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
        # Id of the background generation this session is waiting on. The job
        # itself lives in the process-wide registry in ``shared.jobs``; this is
        # only how a session knows the run is *its* run.
        'job_id': None,
        # Snapshot of the form taken by the Generate callback, not yet handed to
        # the pool. Set before the rerun paints, so the form is already locked.
        'pending_job': None,
        'job_error': None,
        # A provider that failed inside an otherwise successful run.
        'job_notice': None,
        'gallery_page': 0,
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
