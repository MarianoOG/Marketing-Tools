"""Asset Library - browse, download and delete every generated asset.

Run from the asset_generation directory:

    source .venv/bin/activate
    cd asset_generation && streamlit run Home.py
"""

from __future__ import annotations

import mimetypes
from typing import List

import streamlit as st

from prompt_manager import ASSET_DIRS
from shared import jobs
from shared.library import Asset, filter_assets, list_assets, load_bytes, delete_asset
from shared.state import init_session_state

#: Tiles per row and per page. Renders are 2K, so a page is a real cost.
COLUMNS = 4
PAGE_SIZE = 24

ALL = "All"


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


def render_tile(asset: Asset) -> None:
    """One thumbnail plus an expander holding the full view, download and delete.

    The download button lives in the expander on purpose: it needs its bytes at
    render time, and loading every tile's 3-6 MB on every rerun would make the
    grid crawl.
    """
    st.image(str(asset.path), width='stretch')
    st.caption(asset.label)

    with st.expander("Details"):
        st.text(asset.path.name)
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
            delete_asset(asset.path)
            list_assets.clear()
            st.rerun()


@st.fragment(run_every=2)
def watch_jobs() -> None:
    """Wait for a generation started elsewhere without polling the whole grid.

    The count comes from the process-wide registry rather than session state, so
    this also covers a job whose Create tab was closed: when it lands, the app
    rerun below reaches ``jobs.collect()``, which clears the ``list_assets``
    cache, and the new tile appears without anyone clicking anything.
    """
    running = jobs.running_count()
    if not running:
        st.rerun(scope="app")
        return
    st.info(f"{running} generation{'s' if running > 1 else ''} in progress...")


def render_grid(assets: List[Asset]) -> None:
    """Lay the tiles out in rows of :data:`COLUMNS`."""
    for row_start in range(0, len(assets), COLUMNS):
        row = assets[row_start:row_start + COLUMNS]
        for column, asset in zip(st.columns(COLUMNS), row):
            with column:
                render_tile(asset)


def main() -> None:
    st.set_page_config(page_title="Asset Library", page_icon="🎨", layout="wide")
    init_session_state()

    # Retire any generation that landed while the user was standing here; this
    # is what refreshes the listing cache before it is read below.
    jobs.collect()

    st.title("🎨 Asset Library")
    st.caption("Every character, object, location and scene generated so far.")

    # Both shown once: they report on the run that just ended, not on a state the
    # library should keep nagging about.
    if st.session_state.job_error:
        st.warning(f"Last generation failed: {st.session_state.job_error}")
        st.session_state.job_error = None
    if st.session_state.job_notice:
        st.warning(f"One provider failed: {st.session_state.job_notice}")
        st.session_state.job_notice = None
    if jobs.running_count():
        watch_jobs()

    assets = list_assets()
    if not assets:
        st.info("No assets yet. Generate your first one to get started.")
        if st.button("Create an asset", type="primary"):
            st.switch_page("pages/1_Create.py")
        return

    if st.button("＋ Create an asset", type="primary"):
        st.switch_page("pages/1_Create.py")

    st.divider()
    visible = render_filters(assets)
    st.caption(f"{len(visible)} of {len(assets)} assets")

    if not visible:
        st.info("No assets match these filters.")
        return

    st.divider()
    render_grid(paginate(visible))


if __name__ == '__main__':
    main()
