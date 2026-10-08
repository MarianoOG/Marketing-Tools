"""WordPress content tagging. Both steps are long and run as background jobs on a
single-worker pool, so two runs never append to the same files at once."""

from __future__ import annotations

import os
from typing import Dict

from fastapi import APIRouter, HTTPException

from app import jobs
from app.wordpress.analyze import read_metadata, run_analysis, summarize
from app.wordpress.update import run_update

router = APIRouter(prefix="/wordpress", tags=["wordpress"])


def _require(*names: str) -> None:
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise HTTPException(503, f"Missing {', '.join(missing)}. Add it to backend/.env.")


@router.get("/summary")
def get_summary() -> Dict:
    """Counts over everything classified so far."""
    return summarize(read_metadata())


@router.post("/analyze", status_code=202)
def start_analysis() -> Dict:
    """Classify every post in the sitemap that is not classified yet."""
    _require("WP_SITE_URL", "OPENAI_API_KEY")
    return jobs.submit("wordpress", "Analyze website", run_analysis).to_dict()


@router.post("/update-categories", status_code=202)
def start_update() -> Dict:
    """Apply the analysed categories to every still-uncategorised post."""
    _require("WP_SITE_URL", "WP_USERNAME", "WP_APP_PASSWORD")
    return jobs.submit("wordpress", "Update categories", run_update).to_dict()
