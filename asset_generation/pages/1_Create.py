"""Create - generate one asset from a description, a style and some references.

Characters, objects and locations take uploaded reference images, which are
written to a temporary directory for the length of the call and never saved.
Scenes instead pick any number of existing assets out of the library.

The generation itself runs on a background thread (see :mod:`shared.jobs`), so
leaving this page cannot abandon a paid render. While a job is in flight the
whole form is locked and the page waits; when it lands the user is sent to the
library, which already lists the newest asset first.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from generation import QUALITY
from prompt_manager import ASSET_DIRS, STYLES
from shared import jobs
from shared.library import Asset, REFERENCE_TYPES, list_assets
from shared.state import init_session_state

#: Only the friendly spellings. ``ASPECT_RATIOS`` also holds the raw `16:9`,
#: `1:1` and `9:16` keys, which would show up as duplicate options.
ASPECT_RATIO_OPTIONS = ("landscape", "square", "portrait")

#: ``"both"`` is accepted by ``generate_asset`` but is not in any module
#: constant, so this list is written out rather than read from one.
PROVIDER_OPTIONS = ("both", "openai", "gemini")

ASSET_TYPE_OPTIONS = list(ASSET_DIRS)

UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp"]


def slugify(name: str) -> str:
    """Reduce a typed name to something ``save_image`` will accept.

    It rejects path separators outright, and both it and ``generate_both`` call
    ``Path(filename).stem`` - which would quietly truncate ``fox.hero`` to
    ``fox``.
    """
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def render_form(disabled: bool) -> Dict:
    """The whole input side of the page. Returns the raw field values."""
    asset_type = st.radio(
        "Asset type",
        ASSET_TYPE_OPTIONS,
        format_func=str.capitalize,
        horizontal=True,
        key='asset_type',
        disabled=disabled,
    )

    name = st.text_input(
        "Name",
        placeholder="fox_hero",
        help="Used for the filename. Spaces and punctuation become underscores.",
        key='asset_name',
        disabled=disabled,
    )
    description = st.text_area(
        "Description",
        placeholder=(
            "the fox hero holds the lantern up in the night market"
            if asset_type == "scene"
            else "a lanky fox in a patched wool coat, tall ears, tired eyes"
        ),
        help=(
            "The situation to depict."
            if asset_type == "scene"
            else "The subject to design."
        ),
        height=120,
        key='asset_description',
        disabled=disabled,
    )

    style_col, ratio_col, quality_col, provider_col = st.columns(4)
    style = style_col.selectbox("Style", list(STYLES), key='style', disabled=disabled)
    aspect_ratio = ratio_col.selectbox(
        "Aspect ratio", ASPECT_RATIO_OPTIONS, key='aspect_ratio', disabled=disabled
    )
    quality = quality_col.selectbox("Quality", list(QUALITY), key='quality', disabled=disabled)
    provider = provider_col.selectbox(
        "Provider", PROVIDER_OPTIONS, key='provider', disabled=disabled
    )

    return {
        'asset_type': asset_type,
        'name': name,
        'description': description,
        'style': style,
        'aspect_ratio': aspect_ratio,
        'quality': quality,
        'provider': provider,
    }


def render_upload_references(disabled: bool) -> None:
    """Uploader for character / object / location. Nothing here is saved."""
    st.subheader("Reference images")
    st.caption(
        "Optional. Used as inspiration for the world, palette and mood - never "
        "for the art style. These files are not saved."
    )
    st.file_uploader(
        "Upload references",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        key='uploads',
        disabled=disabled,
    )


def render_library_references(disabled: bool) -> None:
    """Multi-select the existing sheets a scene should reproduce."""
    st.subheader("Reference assets")
    st.caption(
        "Scenes treat these as authority: the designs are reproduced faithfully. "
        "Pick any number of characters, objects and locations."
    )

    selected: List[Asset] = []
    for column, asset_type in zip(st.columns(len(REFERENCE_TYPES)), REFERENCE_TYPES):
        options = list_assets(asset_type)
        with column:
            if not options:
                st.caption(f"No {asset_type}s generated yet.")
                continue
            selected.extend(
                st.multiselect(
                    f"{asset_type.capitalize()}s",
                    options,
                    format_func=lambda a: a.label,
                    key=f"scene_refs_{asset_type}",
                    disabled=disabled,
                )
            )

    if selected:
        for column, asset in zip(st.columns(min(len(selected), 6)), selected):
            column.image(str(asset.path), caption=asset.label, width='stretch')


def accept_job() -> None:
    """Button callback: freeze everything the job needs, submit nothing.

    Streamlit runs ``on_click`` before the rerun paints, so the next frame
    already draws the button and the whole form disabled. That closes the window
    in which a second click could start a second paid generation.

    It also means the widgets are still *enabled* here, which is why the whole
    snapshot - including the uploaded bytes - is taken now rather than read back
    off the locked form on the run that submits.
    """
    state = st.session_state

    asset_type = state.asset_type
    blobs: List = []
    library_refs: List[Path] = []
    if asset_type == "scene":
        library_refs = [
            asset.path
            for reference_type in REFERENCE_TYPES
            for asset in state.get(f"scene_refs_{reference_type}") or []
        ]
    else:
        # ``getvalue`` needs the script thread and the live session, so the
        # bytes are read here and the worker only ever sees plain data.
        blobs = [(upload.name, upload.getvalue()) for upload in state.get('uploads') or []]

    state.pending_job = {
        'fields': {
            'asset_type': asset_type,
            'name': slugify(state.asset_name),
            'description': state.asset_description.strip(),
            'style': state.style,
            'aspect_ratio': state.aspect_ratio,
            'quality': state.quality,
            'provider': state.provider,
        },
        'blobs': blobs,
        'library_refs': library_refs,
    }
    state.job_error = None
    state.job_notice = None


@st.fragment(run_every=2)
def watch_job() -> None:
    """Poll the running job without rerunning the rest of the page."""
    if not jobs.is_running():
        # ``st.switch_page`` cannot be called from a fragment, so hand control
        # back to ``main``, which collects the result and redirects.
        st.rerun(scope="app")
        return

    with st.status(f"Generating {jobs.current_label()}...", expanded=True):
        st.write(
            "Running in the background. You can leave this page - the image is "
            "saved either way."
        )


def main() -> None:
    st.set_page_config(page_title="Create - Asset Library", page_icon="✨", layout="wide")
    init_session_state()

    # Retire a job that finished while we were elsewhere, then redirect: the
    # library lists the newest asset first, so it *is* the result view.
    finished = jobs.collect()
    if finished is not None and finished.error is None:
        st.session_state.gallery_page = 0
        st.switch_page("Home.py")

    running = jobs.is_running() or st.session_state.pending_job is not None

    st.title("✨ Create an asset")
    st.caption("Characters, objects and locations are reference sheets; scenes are finished frames.")

    if st.button("← Back to library"):
        st.switch_page("Home.py")

    st.divider()
    fields = render_form(running)

    st.divider()
    # Rendered for the UI only: ``accept_job`` reads the picked references out
    # of session state, so nothing here has to survive to the submitting run.
    if fields['asset_type'] == "scene":
        render_library_references(running)
    else:
        render_upload_references(running)

    st.divider()
    name = slugify(fields['name'])
    description = fields['description'].strip()
    ready = bool(name and description)
    if fields['name'] and not name:
        st.warning("That name has no usable characters - try letters or digits.")
    st.button(
        "Generating..." if running else "Generate",
        type="primary",
        disabled=running or not ready,
        on_click=accept_job,
    )
    if not ready and not running:
        st.caption("A name and a description are required.")

    # The real duplicate guard: idempotent however many times the callback ran.
    # Submitted after the form is rendered, so the locked UI is already painted.
    if st.session_state.pending_job is not None and not st.session_state.job_id:
        try:
            st.session_state.job_id = jobs.submit(**st.session_state.pending_job)
        except Exception as exc:  # otherwise the form stays locked with no reason shown
            st.session_state.job_error = str(exc)
        st.session_state.pending_job = None
        st.rerun()

    if st.session_state.job_id:
        watch_job()

    if st.session_state.job_error:
        st.error(st.session_state.job_error)


if __name__ == '__main__':
    main()
