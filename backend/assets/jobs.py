"""Background generations that outlive the request that started them.

One call can spend real credits, so the API call must not be tied to the client
that asked for it. The work goes to a thread pool: once :func:`submit` returns,
the image will be generated and written to disk whether the frontend tab is
still open, or Claude is still waiting, or not.

The pool threads are non-daemon on purpose - shutting the server down waits for
an in-flight render rather than discarding one that has already been paid for.

The registry lives in the backend process, so every client sees the same jobs:
the frontend's "in progress" banner also covers a render Claude started. A
finished job stays readable until :data:`_KEEP_FINISHED` newer ones have
finished, which leaves any client polling it plenty of time to read the result.
"""

from __future__ import annotations

import tempfile
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from backend.assets.generation import DEFAULT_WORLD, AssetImageGenerator

#: An uploaded reference: (filename, bytes).
Blob = Tuple[str, bytes]

#: How many finished jobs stay readable before the oldest is dropped.
_KEEP_FINISHED = 50

_LOCK = threading.Lock()

#: Two workers: one job at a time per frontend session, but a second session
#: (or Claude) should not queue behind the first.
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="generate")

#: Every job since the server started, oldest first (dicts keep insertion order).
_REGISTRY: Dict[str, "Job"] = {}

_GENERATOR = AssetImageGenerator()


@dataclass
class Job:
    """One submitted generation. ``results`` and ``error`` are filled on finish."""

    id: str
    label: str
    future: Future
    resolved: bool = False
    results: Dict[str, Path | Exception] = field(default_factory=dict)
    #: Set only when the whole job produced nothing.
    error: str | None = None
    #: Set when ``provider="both"`` and one of the two failed: an image did land,
    #: so the run counts as a success, but the other paid call is worth saying.
    warning: str | None = None

    def done(self) -> bool:
        return self.future.done()


def _run(
    fields: Dict,
    blobs: Sequence[Blob],
    library_refs: Sequence[Path],
) -> Dict[str, Path | Exception]:
    """The worker. Touches only the generator and the disk.

    Uploads are written into a ``TemporaryDirectory`` owned by this call, so
    nothing disappears underneath a generation the caller has walked away from.
    The extension is preserved because Gemini reads the mime type off the
    filename and OpenAI infers it from the multipart upload - a suffix-less file
    would send a JPEG labelled as PNG.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        references = list(library_refs)
        for index, (filename, data) in enumerate(blobs):
            suffix = Path(filename).suffix.lower() or ".png"
            path = Path(tmpdir) / f"reference_{index}{suffix}"
            path.write_bytes(data)
            references.append(path)

        result = _GENERATOR.generate_asset(
            fields['asset_type'],
            fields['name'],
            fields['description'],
            fields['style'],
            reference_images=references,
            aspect_ratio=fields['aspect_ratio'],
            quality=fields['quality'],
            provider=fields['provider'],
            world=fields.get('world', DEFAULT_WORLD),
        )

    # ``generate_asset`` returns a bare Path for a single provider and the
    # per-provider dict for "both"; jobs always carry the dict shape.
    return result if isinstance(result, dict) else {fields['provider']: result}


def submit(fields: Dict, blobs: Sequence[Blob], library_refs: Sequence[Path]) -> str:
    """Start a generation on a pool thread and return its job id."""
    job_id = uuid.uuid4().hex
    label = (
        f"{fields['name']} · {fields['asset_type']} · "
        f"{fields.get('world', DEFAULT_WORLD)} · {fields['provider']}"
    )
    future = _EXECUTOR.submit(_run, dict(fields), list(blobs), list(library_refs))

    with _LOCK:
        _REGISTRY[job_id] = Job(id=job_id, label=label, future=future)
    return job_id


def _resolve(job: Job) -> None:
    """Read the future into ``results`` / ``error`` / ``warning``. Never raises."""
    if job.resolved:
        return
    job.resolved = True
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


def _prune() -> None:
    """Drop the oldest finished jobs beyond :data:`_KEEP_FINISHED`. Holds the lock."""
    finished = [job_id for job_id, job in _REGISTRY.items() if job.done()]
    for job_id in finished[:-_KEEP_FINISHED]:
        del _REGISTRY[job_id]


def get(job_id: str) -> Job:
    """One job, resolved if it has finished. Raises ``KeyError`` if unknown -
    which also happens after a server restart."""
    with _LOCK:
        _prune()
        job = _REGISTRY[job_id]
        if job.done():
            _resolve(job)
    return job


def running() -> List[Job]:
    """Every unfinished job, oldest first."""
    with _LOCK:
        return [job for job in _REGISTRY.values() if not job.done()]
