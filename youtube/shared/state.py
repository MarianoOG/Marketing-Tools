"""Session state management for Creator Discovery app."""

import os
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

from youtube_api import YouTubeService


def init_session_state():
    """Initialize all session state keys with defaults."""
    defaults = {
        'search_results': {},
        'selected_channel': None,
        'search_keyword': '',
        'filters': {},
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def get_service() -> Optional[YouTubeService]:
    """Get or create YouTubeService instance."""
    if 'service' not in st.session_state:
        load_dotenv()
        api_key = os.getenv('YOUTUBE_API_KEY')
        if not api_key:
            return None
        try:
            st.session_state.service = YouTubeService(api_key)
        except Exception:
            return None
    return st.session_state.service


def show_api_error():
    """Display API key error message."""
    st.error("YOUTUBE_API_KEY not found in environment. Please add it to .env file.")
    st.info("Get your API key from: https://console.cloud.google.com/")


def require_search_results() -> bool:
    """Check if search results exist, show warning if not."""
    if not st.session_state.get('search_results'):
        st.warning("No search results available. Please perform a search first.")
        if st.button("Go to Search"):
            st.switch_page("Home.py")
        return False
    return True


def require_selected_channel() -> bool:
    """Check if a channel is selected, show warning if not."""
    if not st.session_state.get('selected_channel'):
        st.warning("No creator selected. Please select a creator from results.")
        if st.button("Go to Results"):
            st.switch_page("pages/1_Results.py")
        return False
    return True
