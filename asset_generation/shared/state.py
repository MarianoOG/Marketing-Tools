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
        # Ids of the background generations this session is waiting on. The
        # jobs themselves live in the process-wide registry in ``shared.jobs``;
        # this is only how a session knows which runs are *its* runs.
        'job_ids': [],
        # Snapshot of the form taken by the Generate callback, not yet handed to
        # the pool. Set before the rerun paints, so a double click can't submit
        # the same click twice.
        'pending_job': None,
        # Errors/warnings from jobs that finished since these were last shown.
        'job_errors': [],
        # A provider that failed inside an otherwise successful run.
        'job_notices': [],
        'gallery_page': 0,
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
