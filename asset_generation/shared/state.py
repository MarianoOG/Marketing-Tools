"""Session state and the shared generator instance."""

from __future__ import annotations

import streamlit as st

from generation import DEFAULT_WORLD, AssetImageGenerator
from shared.worlds import migrate_once


@st.cache_resource(show_spinner=False)
def get_generator() -> AssetImageGenerator:
    """One generator for the whole app.

    The constructor only reads ``.env``; both API clients are lazy properties, so
    a missing key still fails per-provider at call time rather than here.
    """
    return AssetImageGenerator()


def init_session_state() -> None:
    """Seed every key the pages read, so no page needs its own guard.

    The pre-world ``img/<asset-type>/`` tree is folded into ``img/default/``
    first: worlds are enumerated by listing ``img/``, so until that has happened
    the four asset-type folders would read as worlds of their own.
    """
    st.session_state['migration_skipped'] = migrate_once()

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
        # The world every page is looking at, and the one anything generated
        # here is written into.
        'current_world': DEFAULT_WORLD,
        # Paths ticked in the library, as strings, for a bulk move or copy. The
        # set - not the tile checkboxes - is the source of truth: a checkbox key
        # only exists while its tile is on screen, so a selection made before
        # paging would otherwise disappear.
        'selection': set(),
        # One-shot result of a move, copy or world edit, shown after the rerun
        # that performed it.
        'bulk_notice': None,
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
