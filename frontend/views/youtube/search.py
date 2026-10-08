"""
Creator Discovery - Search
Find creators for collaboration opportunities (promotions, appearances, sponsorships).

The search runs as a background job in the backend and is saved when it lands,
so leaving this page does not waste the quota it spends: the result shows up
under Recent searches either way.
"""

from datetime import datetime

import streamlit as st

import api
from shared.youtube import RESULTS_PAGE


def open_search(search_id: str) -> None:
    st.session_state.search_id = search_id
    st.session_state.selected_channel = None
    st.switch_page(RESULTS_PAGE)


def start_search(keyword: str) -> None:
    """Search with every filter open - filtering happens on the Results page."""
    try:
        st.session_state.search_job = api.post("/youtube/searches", json={'keyword': keyword})['id']
        st.session_state.search_keyword = keyword
        st.session_state.search_error = None
    except api.ApiError as exc:
        st.session_state.search_error = str(exc)


@st.fragment(run_every=1)
def watch_search() -> None:
    """Stream the job's progress messages; hand over to ``main`` when it ends."""
    job = api.get(f"/jobs/{st.session_state.search_job}")
    if job['status'] not in ("queued", "running"):
        # ``st.switch_page`` cannot be called from a fragment.
        st.rerun(scope="app")
        return
    with st.status("Searching...", expanded=True):
        for message in job['progress']:
            st.write(message)


def finish_search() -> None:
    """Retire a search that ended: open it, or keep the reason it failed."""
    try:
        job = api.get(f"/jobs/{st.session_state.search_job}")
    except api.ApiError as exc:
        st.session_state.search_job = None
        st.session_state.search_error = str(exc)
        return
    if job['status'] in ("queued", "running"):
        return
    st.session_state.search_job = None
    if job['status'] == "failed":
        st.session_state.search_error = job['error']
    elif job['result']['count']:
        open_search(job['result']['search_id'])
    else:
        st.session_state.search_error = "No creators found"


def render_recent_searches() -> None:
    searches = api.get("/youtube/searches")
    if not searches:
        return
    st.divider()
    st.subheader("Recent searches")
    labels = {
        search['id']: (
            f"{search['keyword']} · {search['count']} creators · "
            f"{datetime.fromisoformat(search['created_at']).strftime('%b %d, %Y %H:%M')}"
        )
        for search in searches
    }
    choice_col, open_col = st.columns([4, 1])
    chosen = choice_col.selectbox(
        "Recent searches", list(labels), format_func=labels.get, label_visibility='collapsed'
    )
    if open_col.button("Open", width='stretch'):
        open_search(chosen)


def main():
    """Search page."""
    if st.session_state.search_job:
        finish_search()

    st.title("Creator Discovery")
    st.caption("Find creators for collaboration opportunities")

    # Search input
    keyword = st.text_input(
        "Search for creators:",
        value=st.session_state.get('search_keyword', ''),
        placeholder="e.g., tech reviews, cooking tutorials, fitness tips"
    )

    running = bool(st.session_state.search_job)
    if not keyword and not running:
        st.info("Enter a search term above to discover creators.")
    elif st.button("Search", type="primary", disabled=running):
        start_search(keyword)
        st.rerun()

    if st.session_state.search_job:
        watch_search()
    if st.session_state.search_error:
        st.error(st.session_state.search_error)

    render_recent_searches()


main()
