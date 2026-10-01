"""Asset Library - browse, download, move and delete every generated asset.

One world at a time: the sidebar switcher picks it, and everything below - the
grid, the filters, the bulk bar - is that world's. Assets cross between worlds
only by being moved or duplicated, one at a time from a tile's Details expander
or in bulk from the ticked selection.

Every change goes through a backend tool; images are read straight from the
(read-only) data folder.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import List

import streamlit as st

from backend.assets.library import Asset, filter_assets
from backend.assets.prompt_manager import ASSET_DIRS
from frontend.assets import (
    CREATE_PAGE,
    collect,
    list_assets,
    list_worlds,
    load_bytes,
    render_world_switcher,
    running_count,
)
from frontend.client import call, local_path
from frontend.state import init_session_state

#: Tiles per row and per page. Renders are 2K, so a page is a real cost.
COLUMNS = 4
PAGE_SIZE = 24

ALL = "All"


def _toggle_selection(key: str, path: str) -> None:
    """Mirror one tile's checkbox into the session-wide selection set."""
    if st.session_state[key]:
        st.session_state.selection.add(path)
    else:
        st.session_state.selection.discard(path)


def selected_paths() -> List[Path]:
    """The current selection, pruned of anything no longer on disk.

    An asset deleted from its own expander leaves its path behind in the set;
    dropping it here keeps the next bulk action from failing on a ghost.
    """
    selection = st.session_state.selection
    paths = sorted((Path(p) for p in selection), key=str)
    alive = [path for path in paths if local_path(path).exists()]
    if len(alive) != len(selection):
        st.session_state.selection = {str(path) for path in alive}
    return alive


def transfer(paths: List[Path], target: str, copy: bool) -> None:
    """Move or duplicate assets into ``target``, then rerun with a verdict.

    Per-file failures are collected rather than aborting the batch: a single
    name already taken in the target should not strand the other twenty. The
    outcome goes through session state because the rerun below wipes anything
    written to the page directly.
    """
    verb = "Duplicated" if copy else "Moved"
    done = 0
    failed: List[str] = []
    for path in paths:
        try:
            call("copy_asset" if copy else "move_asset", path=str(path), target_world=target)
            done += 1
            if not copy:
                # The tile is gone from this world, so Streamlit retires its
                # checkbox on its own; only the selection has to be told.
                st.session_state.selection.discard(str(path))
        except Exception as exc:
            failed.append(f"{path.name} - {exc}")

    if failed:
        st.session_state.bulk_notice = (
            'warning',
            f"{verb} {done} of {len(paths)} to **{target}**. " + "; ".join(failed),
        )
    else:
        st.session_state.bulk_notice = (
            'success',
            f"{verb} {done} asset{'s' if done != 1 else ''} to **{target}**.",
        )

    st.rerun()


def render_bulk_bar(targets: List[str]) -> None:
    """Act on every ticked tile at once. Hidden while nothing is ticked."""
    paths = selected_paths()
    if not paths:
        return

    st.info(f"{len(paths)} selected")
    if not targets:
        st.caption("Create another world before moving anything out of this one.")
        return

    target_col, move_col, copy_col, clear_col = st.columns([3, 1, 1, 1])
    target = target_col.selectbox(
        "Move or duplicate to", targets, key='bulk_target', label_visibility='collapsed'
    )
    if move_col.button("Move", key='bulk_move', width='stretch'):
        transfer(paths, target, copy=False)
    if copy_col.button("Duplicate", key='bulk_copy', width='stretch'):
        transfer(paths, target, copy=True)
    if clear_col.button("Clear", key='bulk_clear', width='stretch'):
        for path in paths:
            st.session_state.pop(f"select_{path}", None)
        st.session_state.selection = set()
        st.rerun()


def render_filters(assets: List[Asset]) -> List[Asset]:
    """Three selectboxes built from what is actually on disk. Returns the subset."""
    type_col, style_col, provider_col = st.columns(3)

    types = [ALL] + [t for t in ASSET_DIRS if any(a.asset_type == t for a in assets)]
    styles = [ALL] + sorted({a.style for a in assets if a.style})
    providers = [ALL] + sorted({a.provider for a in assets if a.provider})

    asset_type = type_col.selectbox("Type", types)
    style = style_col.selectbox("Style", styles)
    provider = provider_col.selectbox("Provider", providers)

    return filter_assets(
        assets,
        asset_type=None if asset_type == ALL else asset_type,
        style=None if style == ALL else style,
        provider=None if provider == ALL else provider,
    )


def paginate(assets: List[Asset]) -> List[Asset]:
    """Clamp the stored page to the current result count and slice it out."""
    pages = max(1, -(-len(assets) // PAGE_SIZE))
    page = min(st.session_state.get('gallery_page', 0), pages - 1)
    st.session_state.gallery_page = page

    if pages > 1:
        previous, label, following = st.columns([1, 2, 1])
        if previous.button("← Previous", disabled=page == 0, width='stretch'):
            st.session_state.gallery_page = page - 1
            st.rerun()
        label.markdown(
            f"<div style='text-align:center'>Page {page + 1} of {pages}</div>",
            unsafe_allow_html=True,
        )
        if following.button("Next →", disabled=page >= pages - 1, width='stretch'):
            st.session_state.gallery_page = page + 1
            st.rerun()

    start = page * PAGE_SIZE
    return assets[start:start + PAGE_SIZE]


def render_tile(asset: Asset, targets: List[str]) -> None:
    """One thumbnail plus an expander holding the full view, download and delete.

    The download button lives in the expander on purpose: it needs its bytes at
    render time, and loading every tile's 3-6 MB on every rerun would make the
    grid crawl.

    ``value=`` on the checkbox is what survives pagination: Streamlit drops
    widget state for anything not rendered on the previous run, so the tick has
    to be re-seeded from the selection set every time the tile comes back.
    """
    st.image(str(local_path(asset.path)), width='stretch')
    st.caption(asset.label)

    key = f"select_{asset.path}"
    st.checkbox(
        "Select",
        value=str(asset.path) in st.session_state.selection,
        key=key,
        on_change=_toggle_selection,
        args=(key, str(asset.path)),
    )

    with st.expander("Details"):
        st.text(asset.path.name)
        if targets:
            target = st.selectbox(
                "Move or duplicate to", targets, key=f"target_{asset.path}"
            )
            move_col, copy_col = st.columns(2)
            if move_col.button("Move", key=f"move_{asset.path}", width='stretch'):
                transfer([asset.path], target, copy=False)
            if copy_col.button("Duplicate", key=f"copy_{asset.path}", width='stretch'):
                transfer([asset.path], target, copy=True)
        st.download_button(
            "Download",
            data=load_bytes(asset.path, asset.mtime),
            file_name=asset.path.name,
            mime=mimetypes.guess_type(asset.path.name)[0] or "image/png",
            key=f"download_{asset.path}",
            width='stretch',
        )
        confirmed = st.checkbox("Confirm delete", key=f"confirm_{asset.path}")
        if st.button(
            "Delete",
            type="primary",
            disabled=not confirmed,
            key=f"delete_{asset.path}",
            width='stretch',
        ):
            call("delete_asset", path=str(asset.path))
            st.session_state.selection.discard(str(asset.path))
            st.rerun()


@st.fragment(run_every=2)
def watch_jobs() -> None:
    """Wait for a generation started elsewhere without polling the whole grid.

    The count comes from the backend rather than session state, so this also
    covers a job whose Create tab was closed, or one Claude started: when it
    lands, the app rerun below lists the assets again and the new tile appears
    without anyone clicking anything.
    """
    running = running_count()
    if not running:
        st.rerun(scope="app")
        return
    st.info(f"{running} generation{'s' if running > 1 else ''} in progress...")


def render_grid(assets: List[Asset], targets: List[str]) -> None:
    """Lay the tiles out in rows of :data:`COLUMNS`."""
    for row_start in range(0, len(assets), COLUMNS):
        row = assets[row_start:row_start + COLUMNS]
        for column, asset in zip(st.columns(COLUMNS), row):
            with column:
                render_tile(asset, targets)


def main() -> None:
    init_session_state()

    # Settle this session's generation if it landed while the user stood here,
    # so its outcome shows below.
    collect()

    world = render_world_switcher()
    targets = [name for name in list_worlds() if name != world]

    st.title("🎨 Asset Library")
    st.caption(f"Every character, object, location and scene in **{world}**.")

    # Shown once: they report on the run that just ended, not on a state the
    # library should keep nagging about.
    if st.session_state.bulk_notice:
        kind, text = st.session_state.bulk_notice
        getattr(st, kind)(text)
        st.session_state.bulk_notice = None
    if st.session_state.job_error:
        st.warning(f"Last generation failed: {st.session_state.job_error}")
        st.session_state.job_error = None
    if st.session_state.job_notice:
        st.warning(f"One provider failed: {st.session_state.job_notice}")
        st.session_state.job_notice = None
    if running_count():
        watch_jobs()

    assets = list_assets(world=world)
    if not assets:
        st.info(f"No assets in {world} yet. Generate your first one to get started.")
        if st.button("Create an asset", type="primary"):
            st.switch_page(CREATE_PAGE)
        return

    if st.button("＋ Create an asset", type="primary"):
        st.switch_page(CREATE_PAGE)

    st.divider()
    visible = render_filters(assets)
    st.caption(f"{len(visible)} of {len(assets)} assets")

    # Above the filter result on purpose: a selection stays actionable even when
    # the filters currently hide every tile in it.
    render_bulk_bar(targets)

    if not visible:
        st.info("No assets match these filters.")
        return

    st.divider()
    render_grid(paginate(visible), targets)


main()
