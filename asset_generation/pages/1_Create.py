"""Create - generate one asset from a description, a style and some references.

Characters, objects and locations take uploaded reference images, which are
written to a temporary directory for the length of the call and never saved.
Scenes instead pick any number of existing assets out of the library.
"""

from __future__ import annotations

import mimetypes
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from generation import QUALITY
from prompt_manager import ASSET_DIRS, STYLES
from shared.library import Asset, REFERENCE_TYPES, list_assets, load_bytes
from shared.state import get_generator, init_session_state

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


def render_form() -> Dict:
    """The whole input side of the page. Returns the raw field values."""
    asset_type = st.radio(
        "Asset type",
        ASSET_TYPE_OPTIONS,
        format_func=str.capitalize,
        horizontal=True,
        key='asset_type',
    )

    name = st.text_input(
        "Name",
        placeholder="fox_hero",
        help="Used for the filename. Spaces and punctuation become underscores.",
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
    )

    style_col, ratio_col, quality_col, provider_col = st.columns(4)
    style = style_col.selectbox("Style", list(STYLES))
    aspect_ratio = ratio_col.selectbox("Aspect ratio", ASPECT_RATIO_OPTIONS)
    quality = quality_col.selectbox("Quality", list(QUALITY))
    provider = provider_col.selectbox("Provider", PROVIDER_OPTIONS)

    return {
        'asset_type': asset_type,
        'name': name,
        'description': description,
        'style': style,
        'aspect_ratio': aspect_ratio,
        'quality': quality,
        'provider': provider,
    }


def render_upload_references() -> List:
    """Uploader for character / object / location. Nothing here is saved."""
    st.subheader("Reference images")
    st.caption(
        "Optional. Used as inspiration for the world, palette and mood - never "
        "for the art style. These files are not saved."
    )
    return st.file_uploader(
        "Upload references",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
    ) or []


def render_library_references() -> List[Path]:
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
                )
            )

    if selected:
        for column, asset in zip(st.columns(min(len(selected), 6)), selected):
            column.image(str(asset.path), caption=asset.label, width='stretch')

    return [asset.path for asset in selected]


def generate(fields: Dict, references: Sequence[Path]) -> None:
    """Run one generation and stash the outcome in session state.

    The result is normalised to ``{provider: Path | Exception}``: ``generate_asset``
    returns a bare ``Path`` for a single provider and that dict for ``"both"``,
    where a failing provider's exception sits in its slot so one outage never
    discards the other image.
    """
    with st.status("Generating...", expanded=True) as status:
        st.write(
            f"{fields['provider']} · {fields['style']} · {fields['aspect_ratio']} · "
            f"quality {fields['quality']}"
            + (f" · {len(references)} reference(s)" if references else "")
        )
        try:
            result = get_generator().generate_asset(
                fields['asset_type'],
                fields['name'],
                fields['description'],
                fields['style'],
                reference_images=list(references),
                aspect_ratio=fields['aspect_ratio'],
                quality=fields['quality'],
                provider=fields['provider'],
            )
        except Exception as exc:
            st.session_state.last_results = {}
            status.update(label="Generation failed", state="error")
            st.error(str(exc))
            return

        results = result if isinstance(result, dict) else {fields['provider']: result}
        st.session_state.last_results = results
        st.session_state.last_asset_type = fields['asset_type']

        failures = sum(1 for value in results.values() if isinstance(value, Exception))
        if failures == len(results):
            status.update(label="Generation failed", state="error")
        else:
            status.update(
                label=f"Generated {len(results) - failures} image(s)", state="complete"
            )

    list_assets.clear()


def run_generation(fields: Dict, uploads: List, library_refs: List[Path]) -> None:
    """Validate, materialise uploaded references, and generate.

    Uploads are written into a ``TemporaryDirectory`` that wraps the whole call.
    The extension is preserved because Gemini reads the mime type off the
    filename and OpenAI infers it from the multipart upload - a suffix-less file
    would send a JPEG labelled as PNG. ``generate_both`` joins its thread pool
    before returning, so every read has finished by the time the directory goes.
    """
    if uploads:
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = []
            for index, upload in enumerate(uploads):
                suffix = Path(upload.name).suffix.lower() or ".png"
                path = Path(tmpdir) / f"reference_{index}{suffix}"
                path.write_bytes(upload.getvalue())
                paths.append(path)
            generate(fields, paths)
    else:
        generate(fields, library_refs)


def render_results() -> None:
    """Show the last generation. Rendered from session state, never from the
    button branch: ``st.download_button`` reruns the script on click, which would
    otherwise evaluate the generate button as False and blank this whole panel.
    """
    results = st.session_state.get('last_results') or {}
    if not results:
        return

    st.divider()
    # Named, because the panel outlives a switch to another asset type.
    last_type = st.session_state.get('last_asset_type')
    st.subheader(f"Latest {last_type}" if last_type else "Latest generation")

    for column, (provider, outcome) in zip(st.columns(len(results)), results.items()):
        with column:
            st.markdown(f"**{provider}**")
            if isinstance(outcome, Exception):
                st.error(str(outcome))
                continue
            st.image(str(outcome), width='stretch')
            st.caption(outcome.name)
            st.download_button(
                "Download",
                data=load_bytes(outcome, outcome.stat().st_mtime),
                file_name=outcome.name,
                mime=mimetypes.guess_type(outcome.name)[0] or "image/png",
                key=f"download_result_{provider}",
                width='stretch',
            )


def main() -> None:
    st.set_page_config(page_title="Create - Asset Library", page_icon="✨", layout="wide")
    init_session_state()

    st.title("✨ Create an asset")
    st.caption("Characters, objects and locations are reference sheets; scenes are finished frames.")

    if st.button("← Back to library"):
        st.switch_page("Home.py")

    st.divider()
    fields = render_form()

    st.divider()
    uploads: List = []
    library_refs: List[Path] = []
    if fields['asset_type'] == "scene":
        library_refs = render_library_references()
    else:
        uploads = render_upload_references()

    st.divider()
    name = slugify(fields['name'])
    description = fields['description'].strip()
    ready = bool(name and description)
    if fields['name'] and not name:
        st.warning("That name has no usable characters - try letters or digits.")
    if st.button("Generate", type="primary", disabled=not ready):
        run_generation({**fields, 'name': name, 'description': description}, uploads, library_refs)
    if not ready:
        st.caption("A name and a description are required.")

    render_results()


if __name__ == '__main__':
    main()
