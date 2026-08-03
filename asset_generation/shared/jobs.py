"""Background generations that outlive the script run that started them.

One click can spend real credits, so the API call must not be tied to the page
it was started from. Streamlit stops a script run at its next ``st.*`` call when
the user navigates or reruns, which would abandon a paid render half-way. Here
the work goes to a thread pool instead: once :func:`submit` returns, the image
will be generated and written to disk no matter where the user goes, or whether
the browser tab is still open at all.

The pool threads are non-daemon on purpose - shutting the server down waits for
an in-flight render rather than discarding one that has already been paid for.

The registry, not ``st.session_state``, is the source of truth for "did a job
land". Session state dies with the tab, while ``list_assets`` is a process-wide
``st.cache_data``: if the only record of a finished job lived in the session
that started it, an image saved after the tab closed would stay invisible in the
library forever. Session state keeps exactly one job fact - ``job_id``, i.e.
whether *this* session is the one that should be shown the progress panel and
redirected when it finishes.
"""

from __future__ import annotations

import tempfile
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Sequence, Tuple

import streamlit as st

from generation import AssetImageGenerator
from shared.library import list_assets
from shared.state import get_generator

#: An uploaded reference, read in the script thread: (filename, bytes).
Blob = Tuple[str, bytes]

_LOCK = threading.Lock()


@dataclass
class Job:
    """One submitted generation. ``results`` and ``error`` are filled on collect."""

    id: str
    label: str
    future: Future
    reconciled: bool = False
    results: Dict[str, Path | Exception] = field(default_factory=dict)
    #: Set only when the whole job produced nothing. Suppresses the redirect.
    error: str | None = None
    #: Set when ``provider="both"`` and one of the two failed: an image did land,
    #: so the run counts as a success, but the other paid call is worth saying.
    warning: str | None = None

    def done(self) -> bool:
        return self.future.done()


@st.cache_resource(show_spinner=False)
def _executor() -> ThreadPoolExecutor:
    """One pool for the whole process. Two workers: the UI allows one job per
    session, but a second browser session should not queue behind the first."""
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="generate")


@st.cache_resource(show_spinner=False)
def _registry() -> Dict[str, Job]:
    """Every job submitted since the server started, until it is reconciled."""
    return {}


def _run(
    generator: AssetImageGenerator,
    fields: Dict,
    blobs: Sequence[Blob],
    library_refs: Sequence[Path],
) -> Dict[str, Path | Exception]:
    """The worker. Touches no Streamlit API - only the generator and the disk.

    Uploads are written into a ``TemporaryDirectory`` owned by this call rather
    than by the script run, so nothing disappears underneath a generation the
    user has walked away from. The extension is preserved because Gemini reads
    the mime type off the filename and OpenAI infers it from the multipart
    upload - a suffix-less file would send a JPEG labelled as PNG.

    The form fills either ``blobs`` or ``library_refs``, never both; passing both
    through would simply use both.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        references = list(library_refs)
        for index, (filename, data) in enumerate(blobs):
            suffix = Path(filename).suffix.lower() or ".png"
            path = Path(tmpdir) / f"reference_{index}{suffix}"
            path.write_bytes(data)
            references.append(path)

        result = generator.generate_asset(
            fields['asset_type'],
            fields['name'],
            fields['description'],
            fields['style'],
            reference_images=references,
            aspect_ratio=fields['aspect_ratio'],
            quality=fields['quality'],
            provider=fields['provider'],
        )

    # ``generate_asset`` returns a bare Path for a single provider and the
    # per-provider dict for "both"; jobs always carry the dict shape.
    return result if isinstance(result, dict) else {fields['provider']: result}


def submit(fields: Dict, blobs: Sequence[Blob], library_refs: Sequence[Path]) -> str:
    """Start a generation on a pool thread and return its job id.

    ``blobs`` are the uploaded references, already read into bytes by the caller
    while it still had the script thread. ``get_generator`` is resolved here for
    the same reason: it is an ``st.cache_resource``, which a bare worker thread
    has no context for.
    """
    generator = get_generator()

    job_id = uuid.uuid4().hex
    label = f"{fields['name']} · {fields['asset_type']} · {fields['provider']}"
    future = _executor().submit(
        _run, generator, dict(fields), list(blobs), list(library_refs)
    )

    with _LOCK:
        _registry()[job_id] = Job(id=job_id, label=label, future=future)
    return job_id


def running_count() -> int:
    """Unfinished jobs anywhere in the process, for the library's banner."""
    with _LOCK:
        return sum(1 for job in _registry().values() if not job.done())


def is_running() -> bool:
    """Whether *this* session is waiting on a job."""
    job_id = st.session_state.get('job_id')
    if not job_id:
        return False
    with _LOCK:
        job = _registry().get(job_id)
    return job is not None and not job.done()


def current_label() -> str:
    """Label of this session's job, for the progress panel."""
    job_id = st.session_state.get('job_id')
    with _LOCK:
        job = _registry().get(job_id) if job_id else None
    return job.label if job else "Generating..."


def _outcome(job: Job) -> None:
    """Read the future into ``results`` / ``error`` / ``warning``. Never raises."""
    try:
        job.results = job.future.result()
    except Exception as exc:
        job.error = str(exc)
        return

    failed = {
        provider: value
        for provider, value in job.results.items()
        if isinstance(value, Exception)
    }
    if not failed:
        return

    text = "; ".join(f"{provider}: {exc}" for provider, exc in failed.items())
    if len(failed) == len(job.results):
        job.error = text
    else:
        # One provider of a "both" run died. The other image was still saved, so
        # this must not read as a failed job - but it did cost a call.
        job.warning = text


def collect() -> Job | None:
    """Retire finished jobs. Call at the top of every page.

    Any finished job is reconciled, whichever session submitted it, so the
    ``list_assets`` cache is refreshed even for an image that landed after its
    tab was closed. The return value is this session's job, if it is the one that
    just finished - the caller uses it to decide whether to redirect.
    """
    session_job_id = st.session_state.get('job_id')

    with _LOCK:
        registry = _registry()
        finished = [job for job in registry.values() if job.done() and not job.reconciled]
        for job in finished:
            job.reconciled = True
            registry.pop(job.id, None)
        # A job id with no entry means the server restarted or the cache was
        # cleared. Drop the id rather than leaving the form disabled forever.
        orphaned = bool(session_job_id) and session_job_id not in registry

    for job in finished:
        _outcome(job)
    if finished:
        list_assets.clear()

    mine = next((job for job in finished if job.id == session_job_id), None)
    if mine is not None:
        st.session_state.job_id = None
        st.session_state.job_error = mine.error
        st.session_state.job_notice = mine.warning
        return mine
    if orphaned:
        # Also the two-tab case: another session reconciled our job first, so we
        # lose the redirect and just unlock. Single-job semantics make it rare.
        st.session_state.job_id = None
    return None
