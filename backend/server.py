"""The MCP server: every tool the frontend and Claude can call.

This is the only process that writes to ``DATA_DIR``. Each tool is a thin
wrapper over a function in :mod:`backend.assets` or :mod:`backend.youtube`;
the logic stays in those modules.

Asset paths cross the wire relative to ``DATA_DIR`` (``img/<world>/<type>/<file>``),
so they mean the same thing to every client however the folder is mounted.

Run it with ``uv run backend`` (or the ``backend`` Compose service).
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any, Literal, Optional

from anyio import from_thread, to_thread
from fastmcp import Context, FastMCP
from pydantic import BaseModel

from backend.assets import jobs, library, worlds
from backend.assets.generation import DEFAULT_WORLD, AspectRatio, Quality
from backend.assets.prompt_manager import AssetType
from backend.config import DATA_DIR, HOST, IMG_DIR, PORT
from backend.youtube.pipeline import search_creators as run_creator_search
from backend.youtube.youtube_api import YouTubeService

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "marketing-tools",
    instructions=(
        "Marketing tools. Assets: generate character, object, location and scene "
        "images into worlds, and browse, move, copy or delete them. Generation runs "
        "in the background: start_generation returns a job id to poll with get_job. "
        "YouTube: search for creators to collaborate with and inspect their channels."
    ),
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AssetOut(BaseModel):
    """One image in the library."""

    #: Relative to the data folder, e.g. ``img/default/characters/fox_flat_2d_ab12cd34_openai.png``.
    path: str
    asset_type: str
    world: str
    name: str
    style: str
    provider: str
    uid: Optional[str]
    mtime: float


class AssetPage(BaseModel):
    """A slice of a listing, newest first."""

    items: list[AssetOut]
    total: int
    offset: int


class Upload(BaseModel):
    """A reference image sent with the request. Never saved into the library."""

    filename: str
    data_base64: str


class JobStatus(BaseModel):
    """Where a generation stands. ``results`` maps provider -> saved path."""

    id: str
    label: str
    state: Literal["running", "done", "failed"]
    results: dict[str, str] = {}
    error: Optional[str] = None
    warning: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _relative(path: Path) -> str:
    return str(Path(path).resolve().relative_to(DATA_DIR))


def _library_path(path: str) -> Path:
    """Resolve a client-supplied path and refuse anything outside ``img/``."""
    resolved = (DATA_DIR / path).resolve()
    if not resolved.is_relative_to(IMG_DIR.resolve()):
        raise ValueError(f"not a library path: {path}")
    return resolved


def _asset_out(asset: library.Asset) -> AssetOut:
    return AssetOut(
        path=_relative(asset.path),
        asset_type=asset.asset_type,
        world=asset.world,
        name=asset.name,
        style=asset.style,
        provider=asset.provider,
        uid=asset.uid,
        mtime=asset.mtime,
    )


def _job_status(job: jobs.Job) -> JobStatus:
    if not job.done():
        return JobStatus(id=job.id, label=job.label, state="running")
    return JobStatus(
        id=job.id,
        label=job.label,
        state="failed" if job.error else "done",
        results={
            provider: _relative(value)
            for provider, value in job.results.items()
            if isinstance(value, Path)
        },
        error=job.error,
        warning=job.warning,
    )


def _refuse_while_generating(action: str) -> None:
    """Renames and deletes wait for renders: a pool thread may be about to write
    into the folder being touched."""
    if jobs.running():
        raise ValueError(f"a generation is running; {action} is held until it lands")


_youtube: YouTubeService | None = None


def _youtube_service() -> YouTubeService:
    global _youtube
    if _youtube is None:
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "YOUTUBE_API_KEY is not set (see .env). "
                "Get one at https://console.cloud.google.com/"
            )
        _youtube = YouTubeService(api_key)
    return _youtube


# ---------------------------------------------------------------------------
# Worlds
# ---------------------------------------------------------------------------


@mcp.tool()
def list_worlds() -> list[str]:
    """Every world (a setting that owns its own assets), alphabetically."""
    return worlds.list_worlds()


@mcp.tool()
def create_world(name: str) -> str:
    """Create an empty world. Returns its slug (lowercase, underscores)."""
    return worlds.create_world(name)


@mcp.tool()
def rename_world(world: str, new_name: str) -> str:
    """Rename a world in place. Returns the new slug. Filenames are untouched."""
    _refuse_while_generating("renaming")
    return worlds.rename_world(world, new_name)


@mcp.tool()
def delete_world(world: str) -> None:
    """Delete a world and every asset in it. There is no undo."""
    _refuse_while_generating("deleting")
    worlds.delete_world(world)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


@mcp.tool()
def list_assets(
    world: Optional[str] = None,
    asset_type: Optional[AssetType] = None,
    style: Optional[str] = None,
    provider: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = 50,
) -> AssetPage:
    """List library assets, newest first. Every filter is optional; ``world=None``
    means every world. ``limit=None`` returns everything from ``offset`` on."""
    assets = library.filter_assets(
        library.list_assets(asset_type, world=world), style=style, provider=provider
    )
    end = None if limit is None else offset + limit
    return AssetPage(
        items=[_asset_out(asset) for asset in assets[offset:end]],
        total=len(assets),
        offset=offset,
    )


@mcp.tool()
def delete_asset(path: str) -> None:
    """Delete one asset. ``path`` as returned by list_assets."""
    library.delete_asset(_library_path(path))


@mcp.tool()
def move_asset(path: str, target_world: str) -> str:
    """Move one asset into another world. Returns its new path."""
    return _relative(worlds.move_asset(_library_path(path), target_world))


@mcp.tool()
def copy_asset(path: str, target_world: str) -> str:
    """Duplicate one asset into another world. Returns the new path."""
    return _relative(worlds.copy_asset(_library_path(path), target_world))


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


@mcp.tool()
def start_generation(
    asset_type: AssetType,
    name: str,
    description: str,
    style: Optional[str],
    world: str = DEFAULT_WORLD,
    aspect_ratio: AspectRatio = "landscape",
    quality: Quality = "low",
    provider: Literal["openai", "gemini", "both"] = "both",
    references: list[str] = [],
    uploads: list[Upload] = [],
) -> str:
    """Start rendering one asset in the background and return a job id for get_job.

    ``style`` is a style key, or null to copy the style from the references
    (which then become required). Scenes take ``references``: library paths from
    the same world. Characters, objects and locations take ``uploads``:
    base64 images used as inspiration and never saved. ``provider="both"``
    renders on OpenAI and Gemini at once, so it costs two calls.
    """
    fields = {
        'asset_type': asset_type,
        'name': worlds.slugify(name),
        'description': description.strip(),
        'style': style,
        'aspect_ratio': aspect_ratio,
        'quality': quality,
        'provider': provider,
        'world': world,
    }
    if not fields['name']:
        raise ValueError("the name needs at least one letter or digit")
    if not fields['description']:
        raise ValueError("a description is required")
    blobs = [(upload.filename, base64.b64decode(upload.data_base64)) for upload in uploads]
    library_refs = [_library_path(path) for path in references]
    return jobs.submit(fields, blobs, library_refs)


@mcp.tool()
def get_job(job_id: str) -> JobStatus:
    """The state of one generation: running, done (with saved paths) or failed."""
    try:
        return _job_status(jobs.get(job_id))
    except KeyError:
        raise ValueError(f"no job {job_id!r} (the server may have restarted)") from None


@mcp.tool()
def running_jobs() -> list[JobStatus]:
    """Every generation still in progress, from any client."""
    return [_job_status(job) for job in jobs.running()]


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_creators(
    keyword: str,
    ctx: Context,
    min_views: int = 0,
    max_views: int = 10_000_000,
    min_subscribers: int = 0,
    max_subscribers: int = 100_000_000,
    activity_days: Optional[int] = None,
) -> dict[str, dict[str, Any]]:
    """Find YouTube creators by keyword. Returns channel_id -> channel data with
    metrics (median views, publish interval, engagement, a 0-100 score) and the
    matching videos. Costs YouTube API quota; progress is reported as it goes."""
    service = _youtube_service()
    steps = 0

    def on_progress(message: str) -> None:
        nonlocal steps
        steps += 1
        from_thread.run(ctx.report_progress, steps, None, message)

    return await to_thread.run_sync(
        lambda: run_creator_search(
            service=service,
            keyword=keyword,
            view_range=(min_views, max_views),
            subscriber_range=(min_subscribers, max_subscribers),
            activity_days=activity_days,
            on_progress=on_progress,
        )
    )


@mcp.tool()
def get_latest_videos(uploads_playlist_id: str, max_results: int = 50) -> list[dict[str, Any]]:
    """A channel's most recent uploads with views and publish dates. The playlist
    id is ``uploads_playlist_id`` from search_creators."""
    return _youtube_service().get_channel_latest_videos(uploads_playlist_id, max_results)


def main() -> None:
    """Entry point for ``uv run backend``."""
    left_behind = worlds.ensure_migrated()
    if left_behind:
        logger.warning(
            "Left in the pre-world folders because the name was taken in default: %s",
            ", ".join(left_behind),
        )
    mcp.run(transport="http", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
