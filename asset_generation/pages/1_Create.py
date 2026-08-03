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

#: Every generation runs on both providers; the UI no longer offers a choice.
#: ``generate_asset`` still accepts a single provider for API callers.
PROVIDER = "both"

ASSET_TYPE_OPTIONS = list(ASSET_DIRS)

UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp"]

#: ``build_prompt`` takes ``style=None`` to mean "the references define the
#: style", so the selectbox carries a ``None`` option. Kept last so it is never
#: the default: it is the one choice that cannot render on its own.
STYLE_OPTIONS = list(STYLES) + [None]

#: What the ``None`` option is called on screen, and in the captions that explain it.
FOLLOW_LABEL = "Follow references"


def slugify(name: str) -> str:
    """Reduce a typed name to something ``save_image`` will accept.

    It rejects path separators outright, and the generator calls
    ``Path(filename).stem`` - which would quietly truncate ``fox.hero`` to
    ``fox``.
    """
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def render_form(disabled: bool) -> Dict:
    """The whole input side of the page.

    Returns only the fields ``main`` needs for its own rendering decisions;
    ``accept_job`` reads every field back off session state by widget key.
    """
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

    style_col, ratio_col, quality_col = st.columns(3)
    style = style_col.selectbox(
        "Style",
        STYLE_OPTIONS,
        format_func=lambda s: FOLLOW_LABEL if s is None else s,
        key='style',
        disabled=disabled,
    )
    ratio_col.selectbox(
        "Aspect ratio", ASPECT_RATIO_OPTIONS, key='aspect_ratio', disabled=disabled
    )
    quality_col.selectbox("Quality", list(QUALITY), key='quality', disabled=disabled)

    return {
        'asset_type': asset_type,
        'name': name,
        'description': description,
        'style': style,
    }


def selected_references(asset_type: str) -> List:
    """The reference widgets' current values: library assets for a scene,
    uploaded files otherwise.

    Branching on ``asset_type`` matters: the keys of the other branch survive in
    session state, so a scene would otherwise see uploads left behind by a
    character. Only meaningful once the reference section has been rendered on
    this run.
    """
    state = st.session_state
    if asset_type == "scene":
        return [
            asset
            for reference_type in REFERENCE_TYPES
            for asset in state.get(f"scene_refs_{reference_type}") or []
        ]
    return list(state.get('uploads') or [])


def render_upload_references(disabled: bool, follow: bool) -> None:
    """Uploader for character / object / location. Nothing here is saved.

    ``follow`` flips the caption: with no style picked these images are the
    source of the art style rather than the one thing never taken from them.
    """
    st.subheader("Reference images")
    st.caption(
        "Required here: the art style is copied from these images. "
        "These files are not saved."
        if follow
        else "Optional. Used as inspiration for the world, palette and mood - "
        "never for the art style. These files are not saved."
    )
    st.file_uploader(
        "Upload references",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        key='uploads',
        disabled=disabled,
    )


def render_library_references(disabled: bool, follow: bool) -> None:
    """Multi-select the existing sheets a scene should reproduce."""
    st.subheader("Reference assets")
    st.caption(
        "Scenes treat these as authority: the designs are reproduced faithfully. "
        "Pick any number of characters, objects and locations."
        + (
            " With no style picked each one also keeps its own art style, so "
            "the frame is not unified into one look."
            if follow
            else ""
        )
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
    references = selected_references(asset_type)
    blobs: List = []
    library_refs: List[Path] = []
    if asset_type == "scene":
        library_refs = [asset.path for asset in references]
    else:
        # ``getvalue`` needs the script thread and the live session, so the
        # bytes are read here and the worker only ever sees plain data.
        blobs = [(upload.name, upload.getvalue()) for upload in references]

    state.pending_job = {
        'fields': {
            'asset_type': asset_type,
            'name': slugify(state.asset_name),
            'description': state.asset_description.strip(),
            'style': state.style,
            'aspect_ratio': state.aspect_ratio,
            'quality': state.quality,
            'provider': PROVIDER,
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
    follow = fields['style'] is None
    if fields['asset_type'] == "scene":
        render_library_references(running, follow)
    else:
        render_upload_references(running, follow)

    st.divider()
    name = slugify(fields['name'])
    description = fields['description'].strip()
    # With no style picked there is nothing to render from - ``build_prompt``
    # rejects it without references, so the button is held rather than letting
    # the job fail.
    missing_references = follow and not selected_references(fields['asset_type'])
    ready = bool(name and description) and not missing_references
    if fields['name'] and not name:
        st.warning("That name has no usable characters - try letters or digits.")
    st.button(
        "Generating..." if running else "Generate",
        type="primary",
        disabled=running or not ready,
        on_click=accept_job,
    )
    if not running:
        if not (name and description):
            st.caption("A name and a description are required.")
        if missing_references:
            st.caption(
                f"**{FOLLOW_LABEL}** takes the look from the references, so at "
                "least one is required."
            )

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
