"""The frontend's only way to change anything: call a backend MCP tool.

``call`` opens a short-lived MCP session per call. Streamlit reruns the whole
script on every click, so there is no long-lived connection to keep; against
``localhost`` the handshake costs milliseconds.

Results come back as plain JSON (dicts, lists, strings). A tool error is raised
as :class:`BackendError` carrying the backend's own message, so pages can show
it the way they used to show a ``ValueError``.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Callable, Optional

from fastmcp import Client
from fastmcp.exceptions import ToolError

from backend.config import DATA_DIR as DEFAULT_DATA_DIR

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8765/mcp")

#: Where the frontend reads image files from. Compose mounts the same folder
#: read-only, so the frontend can display files but never change them.
DATA_DIR = Path(os.environ.get("DATA_DIR") or DEFAULT_DATA_DIR).resolve()

#: Generations and searches can take a while; this only bounds a hung backend.
TIMEOUT_SECONDS = 600


class BackendError(Exception):
    """A tool failed. ``str(exc)`` is the backend's message."""


def _clean(message: str) -> str:
    """Drop FastMCP's "Error calling tool 'x': " prefix."""
    prefix, sep, rest = message.partition("': ")
    return rest if sep and prefix.startswith("Error calling tool '") else message


def call(
    tool: str,
    on_progress: Optional[Callable[[str], None]] = None,
    **arguments: Any,
) -> Any:
    """Call one backend tool and return its JSON result.

    ``on_progress`` receives the progress messages a long tool reports while it
    runs (the creator search does), on the calling thread.
    """

    async def progress_handler(progress: float, total: float | None, message: str | None) -> None:
        if on_progress and message:
            on_progress(message)

    async def run() -> Any:
        async with Client(BACKEND_URL, timeout=TIMEOUT_SECONDS) as client:
            result = await client.call_tool(
                tool, arguments, progress_handler=progress_handler if on_progress else None
            )
        content = result.structured_content
        # Non-object results (lists, strings, None) arrive wrapped as {"result": ...}.
        if isinstance(content, dict) and content.keys() == {"result"}:
            return content["result"]
        return content

    try:
        return asyncio.run(run())
    except ToolError as exc:
        raise BackendError(_clean(str(exc))) from None
    except (OSError, RuntimeError) as exc:
        raise BackendError(
            f"Cannot reach the backend at {BACKEND_URL}. Is it running? ({exc})"
        ) from None


def local_path(path: str | Path) -> Path:
    """Where a backend path (relative to the data folder) lives on this machine."""
    return DATA_DIR / path
