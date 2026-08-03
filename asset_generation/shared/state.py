"""Session state and the shared generator instance."""

from __future__ import annotations

import streamlit as st

from generation import AssetImageGenerator


@st.cache_resource(show_spinner=False)
def get_generator() -> AssetImageGenerator:
    """One generator for the whole app.

    The constructor only reads ``.env``; both API clients are lazy properties, so
    a missing key still fails per-provider at call time rather than here.
    """
    return AssetImageGenerator()


def init_session_state() -> None:
    """Seed every key the pages read, so no page needs its own guard."""
    defaults = {
        # {provider: Path | Exception} from the most recent generate. Rendered
        # outside the button branch so a download's rerun cannot blank it.
        'last_results': {},
        'last_asset_type': None,
        'gallery_page': 0,
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
