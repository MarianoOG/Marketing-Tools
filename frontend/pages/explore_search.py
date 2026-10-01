"""
Creator Discovery - Search Page
Find creators for collaboration opportunities (promotions, appearances, sponsorships).

The search runs in the backend (``search_creators``), which needs
YOUTUBE_API_KEY in .env. Get one from: https://console.cloud.google.com/
"""

from typing import Dict

import streamlit as st

from backend.youtube.config import VIEW_PRESETS, SUBSCRIBER_PRESETS
from frontend.client import BackendError, call
from frontend.state import init_session_state
from frontend.youtube_components import RESULTS_PAGE, revive_dates


def process_search(keyword: str, filters: Dict) -> Dict[str, Dict]:
    """Process search with UI progress updates."""
    with st.status("Searching...", expanded=True) as status:
        def on_progress(msg: str):
            st.write(msg)

        try:
            min_views, max_views = filters['view_range']
            min_subs, max_subs = filters['subscriber_range']
            channels = call(
                "search_creators",
                on_progress=on_progress,
                keyword=keyword,
                min_views=min_views,
                max_views=max_views,
                min_subscribers=min_subs,
                max_subscribers=max_subs,
                activity_days=filters.get('activity_days'),
            )
            channels = {cid: revive_dates(data) for cid, data in channels.items()}

            if channels:
                status.update(label=f"Found {len(channels)} creators", state="complete")
            else:
                status.update(label="No creators found", state="error")

            return channels

        except BackendError as e:
            st.error(str(e))
            status.update(label="Search failed", state="error")
            return {}


def main():
    """Search page."""
    init_session_state()

    st.title("Creator Discovery")
    st.caption("Find creators for collaboration opportunities")

    # Search input
    keyword = st.text_input(
        "Search for creators:",
        value=st.session_state.get('search_keyword', ''),
        placeholder="e.g., tech reviews, cooking tutorials, fitness tips"
    )

    if not keyword:
        st.info("Enter a search term above to discover creators.")
        return

    if st.button("Search", type="primary"):
        # Use default "Any" filters - filtering happens on Results page
        default_filters = {
            'view_range': VIEW_PRESETS["Any"],
            'subscriber_range': SUBSCRIBER_PRESETS["Any"],
            'activity_days': None,
        }
        channels = process_search(keyword, default_filters)
        if channels:
            # Store results and navigate to Results page
            st.session_state.search_results = channels
            st.session_state.search_keyword = keyword
            st.switch_page(RESULTS_PAGE)


main()
