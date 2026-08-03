"""Asset Library - read the img/ tree as the one source of truth.

There is no database. Every generated file already carries its own metadata in
its name (``{name}_{style}_{uuid8}_{provider}``), so the listing is a directory
scan plus a filename parse, held in ``st.cache_data`` and cleared whenever the
tree changes.

Files written before the uuid was introduced use ``{name}_{style}_{provider}``
and still parse - :func:`parse_stem` simply reports ``uid=None`` for them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import streamlit as st

from generation import IMG_DIR
from prompt_manager import ASSET_DIRS, STYLES

#: Extensions the two providers can produce, plus webp for uploaded material.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

#: The three types a scene can draw on as references. Scenes are excluded: a
#: scene is a finished frame, not a design sheet to build another frame from.
REFERENCE_TYPES = ("character", "object", "location")

#: The uuid slug appended by ``generate_asset``. No style key ends in an 8-char
#: hex run (`2d`, `cel`, `clay`, `storybook`, `1930s`, ...), so this pattern
#: cleanly separates the current naming scheme from the legacy one.
_UID_RE = re.compile(r"^[0-9a-f]{8}$")

#: Longest first, so `watercolor_storybook` is matched before `storybook` could
#: ever be considered a style on its own.
_STYLES_BY_LENGTH = sorted(STYLES, key=len, reverse=True)

_PROVIDERS = ("openai", "gemini")


@dataclass(frozen=True)
class Asset:
    """One image on disk, with everything its filename encodes.

    Frozen because these are used directly as ``st.multiselect`` options: the
    widget needs them hashable, and it compares by value across reruns (the
    cached list is unpickled fresh each time, so identity never matches).
    """

    path: Path
    asset_type: str
    name: str
    style: str
    provider: str
    uid: Optional[str]
    mtime: float

    @property
    def label(self) -> str:
        """One-line description for captions and multiselect options."""
        parts = [self.name] + [p for p in (self.style, self.provider) if p]
        return " · ".join(parts)


def parse_stem(stem: str, asset_type: str, path: Path, mtime: float) -> Asset:
    """Read ``{name}_{style}_{uuid8}_{provider}`` back into an :class:`Asset`.

    Parsed right to left, because the name is the only part that may itself
    contain underscores. Anything that does not fit - a hand-dropped file, a
    scheme from the future - degrades to a name-only asset rather than being
    hidden from the gallery.
    """
    remainder = stem
    provider = ""
    uid: Optional[str] = None
    style = ""

    for candidate in _PROVIDERS:
        if remainder.endswith(f"_{candidate}"):
            provider = candidate
            remainder = remainder[: -len(candidate) - 1]
            break

    head, _, tail = remainder.rpartition("_")
    if head and _UID_RE.match(tail):
        uid = tail
        remainder = head

    for candidate in _STYLES_BY_LENGTH:
        if remainder.endswith(f"_{candidate}"):
            style = candidate
            remainder = remainder[: -len(candidate) - 1]
            break

    return Asset(
        path=path,
        asset_type=asset_type,
        name=remainder or stem,
        style=style,
        provider=provider,
        uid=uid,
        mtime=mtime,
    )


@st.cache_data(show_spinner=False)
def list_assets(asset_type: Optional[str] = None) -> List[Asset]:
    """Every asset on disk, newest first. ``None`` means all four types.

    Cached, so call ``list_assets.clear()`` after writing or deleting a file.
    """
    types = [asset_type] if asset_type else list(ASSET_DIRS)
    assets: List[Asset] = []
    for type_name in types:
        directory = IMG_DIR / ASSET_DIRS[type_name]
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
                continue
            assets.append(
                parse_stem(path.stem, type_name, path, path.stat().st_mtime)
            )
    return sorted(assets, key=lambda a: a.mtime, reverse=True)


@st.cache_data(show_spinner=False, max_entries=32)
def load_bytes(path: Path, mtime: float) -> bytes:
    """Read an image for download. ``mtime`` is a cache key, not an argument.

    Capped at 32 entries: a 2K render is 3-6 MB, and an uncapped cache would
    grow for the whole session as the user browses.
    """
    return path.read_bytes()


def delete_asset(path: Path) -> None:
    """Delete one generated image, refusing anything outside ``img/``."""
    resolved = path.resolve()
    if not resolved.is_relative_to(IMG_DIR.resolve()):
        raise ValueError(f"refusing to delete outside the image directory: {path}")
    resolved.unlink()


def filter_assets(
    assets: List[Asset],
    asset_type: Optional[str] = None,
    style: Optional[str] = None,
    provider: Optional[str] = None,
) -> List[Asset]:
    """Narrow a listing. ``None`` on any field means "no constraint"."""
    return [
        asset
        for asset in assets
        if (asset_type is None or asset.asset_type == asset_type)
        and (style is None or asset.style == style)
        and (provider is None or asset.provider == provider)
    ]
