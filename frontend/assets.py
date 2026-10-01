"""Frontend helpers shared by the three Create pages.

Everything here either calls the backend or reads a file from the read-only
data folder. Asset paths stay relative to the data folder, exactly as the
backend returns them, and are only joined with :data:`client.DATA_DIR` at the
moment a file is displayed or downloaded.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import streamlit as st

from backend.assets.library import Asset
from backend.assets.prompt_manager import ASSET_DIRS
from frontend.client import BackendError, call, local_path

LIBRARY_PAGE = "pages/create_library.py"
CREATE_PAGE = "pages/create_asset.py"
WORLDS_PAGE = "pages/create_worlds.py"


def list_worlds() -> List[str]:
    return call("list_worlds")


def list_assets(asset_type: Optional[str] = None, world: Optional[str] = None) -> List[Asset]:
    """Every asset of one type / world, newest first. ``path`` stays relative."""
    page = call("list_assets", world=world, asset_type=asset_type, limit=None)
    return [Asset(**{**item, 'path': Path(item['path'])}) for item in page['items']]


@st.cache_data(show_spinner=False, max_entries=32)
def load_bytes(path: Path, mtime: float) -> bytes:
    """Read an image for download. ``mtime`` is a cache key, not an argument.

    Capped at 32 entries: a 2K render is 3-6 MB, and an uncapped cache would
    grow for the whole session as the user browses.
    """
    return local_path(path).read_bytes()


def running_count() -> int:
    """Unfinished generations from any client, for the banners."""
    return len(call("running_jobs"))


def is_running() -> bool:
    """Whether *this* session is waiting on a job that is still rendering."""
    job_id = st.session_state.get('job_id')
    if not job_id:
        return False
    try:
        return call("get_job", job_id=job_id)['state'] == "running"
    except BackendError:
        return False


def current_label() -> str:
    """Label of this session's job, for the progress panel."""
    job_id = st.session_state.get('job_id')
    try:
        return call("get_job", job_id=job_id)['label'] if job_id else "Generating..."
    except BackendError:
        return "Generating..."


def collect() -> Optional[dict]:
    """Settle this session's job once it has finished. Call at the top of a page.

    Returns the job status if it just finished, so the caller can decide whether
    to redirect. An id the backend no longer knows (it restarted) is dropped
    rather than leaving the form locked forever.
    """
    job_id = st.session_state.get('job_id')
    if not job_id:
        return None
    try:
        job = call("get_job", job_id=job_id)
    except BackendError:
        st.session_state.job_id = None
        return None
    if job['state'] == "running":
        return None

    st.session_state.job_id = None
    st.session_state.job_error = job['error']
    st.session_state.job_notice = job['warning']
    return job


def _drop_world_scoped_state() -> None:
    """Forget everything that only made sense in the world we just left.

    Streamlit is not guaranteed to prune a multiselect's value when its options
    disappear, and ``accept_job`` reads ``scene_refs_*`` straight out of session
    state - so without this a world switch could still submit references from the
    old world. The library's tile checkboxes go for the same reason. Safe to
    delete those widget keys here because the switcher is drawn before any of
    them: Streamlit only objects to touching a widget's state after the widget
    itself has been created on this run.
    """
    state = st.session_state
    for asset_type in ASSET_DIRS:
        state.pop(f"scene_refs_{asset_type}", None)
    for key in [key for key in state if key.startswith("select_")]:
        del state[key]
    state.selection = set()
    state.gallery_page = 0


def render_world_switcher(disabled: bool = False, link: bool = True) -> str:
    """The sidebar world picker, shared by every Create page. Returns the active world.

    The selectbox deliberately carries no ``key``: ``current_world`` stays a
    plain session value that any page can assign to after a world is created,
    renamed or deleted. Binding the widget to it directly would make those
    assignments illegal on the run that performs them. Passing ``index`` instead
    means the widget follows ``current_world`` in both directions.

    It also reconciles ``current_world`` with what is actually on disk, so a
    world renamed or deleted elsewhere cannot leave the picker pointing at
    something that no longer exists.

    ``link=False`` drops the link to the Worlds page, for the Worlds page itself.
    """
    worlds = list_worlds()
    current = st.session_state.get('current_world')
    if current not in worlds:
        current = worlds[0]

    with st.sidebar:
        chosen = st.selectbox(
            "World",
            worlds,
            index=worlds.index(current),
            disabled=disabled,
            help="Assets are grouped by world. A scene can only use references "
            "from the world it is generated into.",
        )
        if disabled:
            st.caption("Locked while a generation is running.")
        if link:
            st.page_link(WORLDS_PAGE, label="Manage worlds", icon="🌍")

    if chosen != st.session_state.get('current_world'):
        st.session_state.current_world = chosen
        _drop_world_scoped_state()
        st.rerun()

    return chosen
