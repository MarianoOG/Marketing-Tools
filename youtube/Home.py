#!/usr/bin/env python3
"""
Creator Discovery - Home Page (Search)
Find creators for collaboration opportunities (promotions, appearances, sponsorships).

Installation:
    1. pip install -r requirements.txt
    2. Create a .env file in the same directory with: YOUTUBE_API_KEY=your_api_key_here
    3. Get your API key from: https://console.cloud.google.com/
    4. Run: streamlit run Home.py
"""

from typing import Dict

import streamlit as st

from config import VIEW_PRESETS, SUBSCRIBER_PRESETS
from pipeline import search_creators, SearchError
from shared.state import init_session_state, get_service, show_api_error


def process_search(service, keyword: str, filters: Dict) -> Dict[str, Dict]:
    """Process search with UI progress updates."""
    with st.status("Searching...", expanded=True) as status:
        def on_progress(msg: str):
            st.write(msg)

        try:
            channels = search_creators(
                service=service,
                keyword=keyword,
                view_range=filters['view_range'],
                subscriber_range=filters['subscriber_range'],
                activity_days=filters.get('activity_days'),
                on_progress=on_progress,
            )

            if channels:
                status.update(label=f"Found {len(channels)} creators", state="complete")
            else:
                status.update(label="No creators found", state="error")

            return channels

        except SearchError as e:
            st.error(str(e))
            status.update(label="Search failed", state="error")
            return {}


def main():
    """Home page - Search functionality."""
    st.set_page_config(page_title="Creator Discovery", page_icon="🔍", layout="wide")

    init_session_state()
    service = get_service()

    if service is None:
        show_api_error()
        return

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
        channels = process_search(service, keyword, default_filters)
        if channels:
            # Store results and navigate to Results page
            st.session_state.search_results = channels
            st.session_state.search_keyword = keyword
            st.switch_page("pages/1_Results.py")


if __name__ == '__main__':
    main()
