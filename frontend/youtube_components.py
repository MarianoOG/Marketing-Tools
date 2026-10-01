"""Shared helpers for the Creator Discovery pages."""

from datetime import datetime
from typing import Dict, List

import streamlit as st

from backend.youtube.config import ACTIVITY_PRESETS, SUBSCRIBER_PRESETS, VIEW_PRESETS
from backend.youtube.sorting import SORT_OPTIONS
from frontend.client import call

SEARCH_PAGE = "pages/explore_search.py"
RESULTS_PAGE = "pages/explore_results.py"
CREATOR_PAGE = "pages/explore_creator.py"

#: Fields that cross the wire as ISO strings and are compared as datetimes here.
_DATE_FIELDS = ('created_at', 'last_published', 'published_at')


def revive_dates(record: Dict) -> Dict:
    """Turn the ISO date strings of one channel or video back into datetimes."""
    for field in _DATE_FIELDS:
        if isinstance(record.get(field), str):
            record[field] = datetime.fromisoformat(record[field])
    for video in record.get('videos', []):
        revive_dates(video)
    return record


@st.cache_data(show_spinner=False)
def cached_get_channel_latest_videos(uploads_playlist_id: str, max_results: int = 10) -> List[Dict]:
    """Cached wrapper for fetching channel's latest videos."""
    videos = call("get_latest_videos", uploads_playlist_id=uploads_playlist_id, max_results=max_results)
    return [revive_dates(video) for video in videos]


def require_search_results() -> bool:
    """Check if search results exist, show warning if not."""
    if not st.session_state.get('search_results'):
        st.warning("No search results available. Please perform a search first.")
        if st.button("Go to Search"):
            st.switch_page(SEARCH_PAGE)
        return False
    return True


def require_selected_channel() -> bool:
    """Check if a channel is selected, show warning if not."""
    if not st.session_state.get('selected_channel'):
        st.warning("No creator selected. Please select a creator from results.")
        if st.button("Go to Results"):
            st.switch_page(RESULTS_PAGE)
        return False
    return True


def render_filters() -> Dict:
    """Render horizontal filter dropdowns."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        view_preset = st.selectbox(
            "Views",
            options=list(VIEW_PRESETS.keys()),
            index=0,
            help="Filter by median view count"
        )

    with col2:
        sub_preset = st.selectbox(
            "Subscribers",
            options=list(SUBSCRIBER_PRESETS.keys()),
            index=2,
            help="Filter by subscriber count"
        )

    with col3:
        activity_preset = st.selectbox(
            "Activity",
            options=list(ACTIVITY_PRESETS.keys()),
            index=1,
            help="Filter by recent activity"
        )

    with col4:
        sort_by = st.selectbox(
            "Sort by",
            options=list(SORT_OPTIONS.keys()),
            index=0,
            help="Sort results"
        )

    return {
        'view_range': VIEW_PRESETS[view_preset],
        'subscriber_range': SUBSCRIBER_PRESETS[sub_preset],
        'activity_days': ACTIVITY_PRESETS[activity_preset],
        'sort_by': SORT_OPTIONS[sort_by],
    }
