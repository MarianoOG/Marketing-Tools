"""Shared UI components for Creator Discovery app."""

from typing import Dict, List

import streamlit as st

from config import VIEW_PRESETS, SUBSCRIBER_PRESETS, ACTIVITY_PRESETS
from sorting import SORT_OPTIONS
from youtube_api import YouTubeService


@st.cache_data(show_spinner=False)
def cached_get_channel_latest_videos(_service: YouTubeService, uploads_playlist_id: str, max_results: int = 10) -> List[Dict]:
    """Cached wrapper for fetching channel's latest videos."""
    return _service.get_channel_latest_videos(uploads_playlist_id, max_results)


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
