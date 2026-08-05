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
library forever. Session state keeps only which job ids - ``job_ids`` - belong
to *this* session, i.e. which ones should show up in its progress panel.

A session may have several jobs in flight at once - the pool has more than one
worker, and the UI no longer locks the form while a job runs. Submitting the
same request twice while the first is still running does not start a second
paid render: :func:`submit` recognizes the duplicate and attaches the caller to
the existing job instead.
"""

from __future__ import annotations

import hashlib
import tempfile
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import streamlit as st

from generation import AssetImageGenerator
from shared.library import list_assets
from shared.state import get_generator

#: An uploaded reference, read in the script thread: (filename, bytes).
Blob = Tuple[str, bytes]

#: Each job makes 2 provider calls, so this bounds outbound calls to 2x this
#: within typical provider rate limits. Submissions beyond this queue inside
#: the executor itself - no separate queue data structure needed.
MAX_WORKERS = 4

_LOCK = threading.Lock()


@dataclass
class Job:
    """One submitted generation. ``results`` and ``error`` are filled on collect."""

    id: str
    label: str
    future: Future
    #: Hash of the request (fields + references). Lets a second, identical
    #: submission attach to this job instead of paying for a duplicate render.
    dedup_key: str = ""
    reconciled: bool = False
    results: Dict[str, Path | Exception] = field(default_factory=dict)
    #: Set only when the whole job produced nothing.
    error: str | None = None
    #: Set when ``provider="both"`` and one of the two failed: an image did land,
    #: so the run counts as a success, but the other paid call is worth saying.
    warning: str | None = None

    def done(self) -> bool:
        return self.future.done()


@st.cache_resource(show_spinner=False)
def _executor() -> ThreadPoolExecutor:
    """One pool for the whole process, shared by every session."""
    return ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="generate")


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


def _dedup_key(fields: Dict, blobs: Sequence[Blob], library_refs: Sequence[Path]) -> str:
    """Hash a request so an identical one can be recognized while it runs.

    Filenames are not part of the key - two uploads of the same image under
    different names are still the same request. Order is preserved for both
    blobs and library refs, since reference order can affect the prompt.
    """
    hasher = hashlib.sha256()
    for key in sorted(fields):
        hasher.update(f"{key}={fields[key]}\x00".encode())
    for _, data in blobs:
        hasher.update(hashlib.sha256(data).digest())
    for path in library_refs:
        hasher.update(str(path).encode())
        hasher.update(b"\x00")
    return hasher.hexdigest()


def submit(
    fields: Dict, blobs: Sequence[Blob], library_refs: Sequence[Path]
) -> Tuple[str, bool]:
    """Start a generation on a pool thread and return its job id.

    ``blobs`` are the uploaded references, already read into bytes by the caller
    while it still had the script thread. ``get_generator`` is resolved here for
    the same reason: it is an ``st.cache_resource``, which a bare worker thread
    has no context for.

    If an unfinished job already exists for the exact same request, no new
    render is started - the returned id points at that job instead, and the
    second element is ``True`` so the caller can say so. This is the guard
    against paying twice for one render.
    """
    generator = get_generator()
    key = _dedup_key(fields, blobs, library_refs)

    with _LOCK:
        registry = _registry()
        existing = next(
            (job for job in registry.values() if job.dedup_key == key and not job.done()),
            None,
        )
        if existing is not None:
            return existing.id, True

        job_id = uuid.uuid4().hex
        label = f"{fields['name']} · {fields['asset_type']} · {fields['provider']}"
        future = _executor().submit(
            _run, generator, dict(fields), list(blobs), list(library_refs)
        )
        registry[job_id] = Job(id=job_id, label=label, future=future, dedup_key=key)
    return job_id, False


def running_count() -> int:
    """Unfinished jobs anywhere in the process, for the library's banner."""
    with _LOCK:
        return sum(1 for job in _registry().values() if not job.done())


def session_jobs() -> List[Job]:
    """This session's jobs still in the registry, running or freshly finished."""
    ids = st.session_state.get('job_ids', [])
    with _LOCK:
        registry = _registry()
        return [registry[job_id] for job_id in ids if job_id in registry]


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


def collect() -> List[Job]:
    """Retire finished jobs. Call at the top of every page.

    Any finished job is reconciled, whichever session submitted it, so the
    ``list_assets`` cache is refreshed even for an image that landed after its
    tab was closed. The return value is this session's jobs that finished on
    this call, so the caller can report each one's error or warning - several
    can land in the same poll now that a session may have more than one job
    in flight.
    """
    session_ids = list(st.session_state.get('job_ids', []))

    with _LOCK:
        registry = _registry()
        finished = [job for job in registry.values() if job.done() and not job.reconciled]
        for job in finished:
            job.reconciled = True
            registry.pop(job.id, None)
        # An id with no entry left means it was reconciled elsewhere (another
        # tab, or above) or the server restarted. Either way, stop tracking it.
        still_registered = {job_id for job_id in session_ids if job_id in registry}

    for job in finished:
        _outcome(job)
    if finished:
        list_assets.clear()

    st.session_state.job_ids = [job_id for job_id in session_ids if job_id in still_registered]

    finished_ids = set(session_ids)
    return [job for job in finished if job.id in finished_ids]
