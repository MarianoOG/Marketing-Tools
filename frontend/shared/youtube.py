"""Shared UI for the Creator Discovery pages."""

from typing import Dict, Optional

import streamlit as st

import api

SEARCH_PAGE = "views/youtube/search.py"
RESULTS_PAGE = "views/youtube/results.py"
CREATOR_PAGE = "views/youtube/creator.py"
INSIGHTS_PAGE = "views/youtube/insights.py"


def open_insights(channel_id: Optional[str] = None) -> None:
    """Audience Insights for the current search, or one creator in it."""
    st.session_state.insights_channel = channel_id
    st.session_state.insights_id = None
    st.switch_page(INSIGHTS_PAGE)


def adopt_from_url(state_key: str, param: str) -> Optional[str]:
    """Session value first, the URL second - then mirror it back into the URL.

    Page switches clear query params and a refresh clears session state, so
    each page writes its ids back to the URL to survive either.
    """
    value = st.session_state.get(state_key) or st.query_params.get(param)
    st.session_state[state_key] = value
    if value:
        st.query_params[param] = value
    return value


def render_filters() -> Dict:
    """Render horizontal filter dropdowns. Returns preset labels for the API."""
    options = api.options("youtube")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        view_preset = st.selectbox(
            "Views",
            options=options['view_presets'],
            index=0,
            help="Filter by median view count"
        )

    with col2:
        sub_preset = st.selectbox(
            "Subscribers",
            options=options['subscriber_presets'],
            index=2,
            help="Filter by subscriber count"
        )

    with col3:
        activity_preset = st.selectbox(
            "Activity",
            options=options['activity_presets'],
            index=1,
            help="Filter by recent activity"
        )

    with col4:
        sort_by = st.selectbox(
            "Sort by",
            options=options['sort_options'],
            index=0,
            help="Sort results"
        )

    return {
        'views': view_preset,
        'subscribers': sub_preset,
        'activity': activity_preset,
        'sort_by': sort_by,
    }
