"""Creator Discovery - search YouTube, then filter, sort and inspect the result.

A search runs as a background job (it pages through up to a thousand results)
and is saved to disk when it lands; filtering and sorting a saved search is
free, so the Results page can re-ask on every widget change.

Audience Insights mines the comments of a saved search's most-discussed videos
for content ideas. It also runs as a job, and its result is saved alongside the
searches.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import jobs
from app.youtube.comments import estimate_run, select_videos
from app.youtube.config import (
    ACTIVITY_PRESETS,
    COMMENTS_PER_VIDEO_OPTIONS,
    DEFAULT_COMMENTS_PER_VIDEO,
    DEFAULT_INSIGHT_VIDEOS,
    INSIGHTS_MODEL,
    MAX_INSIGHT_VIDEOS,
    MAX_VIDEOS_PER_CHANNEL,
    SUBSCRIBER_PRESETS,
    VIEW_PRESETS,
)
from app.youtube.filters import filter_channels
from app.youtube.insights import run_insights
from app.youtube.pipeline import search_creators
from app.youtube.presenters import channel_view, insights_view, upload_pattern
from app.youtube.sorting import SORT_OPTIONS, sort_channels
from app.youtube.store import (
    list_insights,
    list_searches,
    load_insights,
    load_search,
    save_insights,
    save_search,
)
from app.youtube.youtube_api import YouTubeService

router = APIRouter(prefix="/youtube", tags=["youtube"])


class SearchRequest(BaseModel):
    keyword: str


class InsightsRequest(BaseModel):
    channel_id: Optional[str] = None
    videos: int = DEFAULT_INSIGHT_VIDEOS
    per_video: int = DEFAULT_COMMENTS_PER_VIDEO
    language: str = "English"


def _service() -> YouTubeService:
    """A fresh client per job or request.

    The underlying ``httplib2`` connection is not thread-safe, and searches and
    page requests run on different threads. Building one is cheap: the
    discovery document ships with the library.
    """
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        raise HTTPException(
            503,
            "YOUTUBE_API_KEY not found in environment. Please add it to backend/.env. "
            "Get your API key from: https://console.cloud.google.com/",
        )
    return YouTubeService(api_key)


def _search(search_id: str) -> Dict:
    try:
        return load_search(search_id)
    except KeyError as exc:
        raise HTTPException(404, f"no saved search {search_id!r}") from exc


def _preset(presets: Dict, label: str, field: str):
    if label not in presets:
        raise HTTPException(422, f"{field} must be one of {list(presets)}")
    return presets[label]


@router.get("/options")
def options() -> Dict:
    """The preset labels the Results filters offer, in display order."""
    return {
        "view_presets": list(VIEW_PRESETS),
        "subscriber_presets": list(SUBSCRIBER_PRESETS),
        "activity_presets": list(ACTIVITY_PRESETS),
        "sort_options": list(SORT_OPTIONS),
        "insight_videos": {"default": DEFAULT_INSIGHT_VIDEOS, "max": MAX_INSIGHT_VIDEOS},
        "comments_per_video": COMMENTS_PER_VIDEO_OPTIONS,
        "default_comments_per_video": DEFAULT_COMMENTS_PER_VIDEO,
    }


@router.post("/searches", status_code=202)
def start_search(request: SearchRequest) -> Dict:
    """Search with every filter open - filtering happens on the saved result."""
    keyword = request.keyword.strip()
    if not keyword:
        raise HTTPException(422, "Enter a search term.")
    service = _service()

    def run(progress) -> Dict:
        channels = search_creators(
            service=service,
            keyword=keyword,
            view_range=VIEW_PRESETS["Any"],
            subscriber_range=SUBSCRIBER_PRESETS["Any"],
            activity_days=None,
            on_progress=progress,
        )
        return {"search_id": save_search(keyword, channels), "count": len(channels)}

    return jobs.submit("youtube", f"Search: {keyword}", run).to_dict()


@router.get("/searches")
def get_searches() -> List[Dict]:
    """Saved searches, newest first."""
    return list_searches()


@router.get("/searches/{search_id}/channels")
def get_channels(
    search_id: str,
    views: str = "Any",
    subscribers: str = "Any",
    activity: str = "Any",
    sort_by: str = "Relevance",
) -> Dict:
    """A saved search, filtered and sorted by preset labels from ``/options``."""
    search = _search(search_id)
    filtered = filter_channels(
        search["channels"],
        _preset(VIEW_PRESETS, views, "views"),
        _preset(SUBSCRIBER_PRESETS, subscribers, "subscribers"),
        _preset(ACTIVITY_PRESETS, activity, "activity"),
    )
    ordered = sort_channels(filtered, _preset(SORT_OPTIONS, sort_by, "sort_by"))
    return {
        "keyword": search["keyword"],
        "total": len(search["channels"]),
        "channels": [channel_view(channel) for channel in ordered],
    }


@router.get("/searches/{search_id}/channels/{channel_id}")
def get_channel(search_id: str, channel_id: str) -> Dict:
    channel = _search(search_id)["channels"].get(channel_id)
    if channel is None:
        raise HTTPException(404, "Channel data not found.")
    return channel_view(channel)


@lru_cache(maxsize=256)
def _latest_videos(uploads_playlist_id: str, max_results: int) -> List[Dict]:
    """Cached: every creator page view would otherwise spend quota again."""
    return _service().get_channel_latest_videos(uploads_playlist_id, max_results)


@router.get("/playlists/{uploads_playlist_id}/videos")
def get_latest_videos(uploads_playlist_id: str, max_results: int = 50) -> Dict:
    """A channel's latest uploads plus their six-month upload pattern."""
    videos = _latest_videos(uploads_playlist_id, max_results)
    return {"videos": videos, "upload_pattern": upload_pattern(videos)}


def _insight_videos(search: Dict, channel_id: Optional[str], videos: int, per_video: int) -> List[Dict]:
    if channel_id and channel_id not in search["channels"]:
        raise HTTPException(404, "Channel data not found.")
    if not 1 <= videos <= MAX_INSIGHT_VIDEOS:
        raise HTTPException(422, f"videos must be between 1 and {MAX_INSIGHT_VIDEOS}")
    if per_video not in COMMENTS_PER_VIDEO_OPTIONS:
        raise HTTPException(422, f"per_video must be one of {COMMENTS_PER_VIDEO_OPTIONS}")
    return select_videos(search["channels"], videos, channel_id)


@router.get("/searches/{search_id}/insights/estimate")
def estimate_insights(
    search_id: str,
    channel_id: Optional[str] = None,
    videos: int = DEFAULT_INSIGHT_VIDEOS,
    per_video: int = DEFAULT_COMMENTS_PER_VIDEO,
) -> Dict:
    """The videos a run would read and what it would cost. Spends nothing."""
    chosen = _insight_videos(_search(search_id), channel_id, videos, per_video)
    return {
        **estimate_run(chosen, per_video),
        "model": INSIGHTS_MODEL,
        "analysis_available": bool(os.getenv("OPENAI_API_KEY")),
        "per_channel_cap": None if channel_id else MAX_VIDEOS_PER_CHANNEL,
    }


@router.post("/searches/{search_id}/insights", status_code=202)
def start_insights(search_id: str, request: InsightsRequest) -> Dict:
    """Fetch the comments and analyse them in the background; the run is saved."""
    search = _search(search_id)
    chosen = _insight_videos(search, request.channel_id, request.videos, request.per_video)
    if not chosen:
        raise HTTPException(422, "None of these videos has comments.")
    language = request.language.strip() or "English"
    service = _service()
    with_analysis = bool(os.getenv("OPENAI_API_KEY"))

    def run(progress) -> Dict:
        record = run_insights(
            service, search, chosen, request.per_video, language,
            request.channel_id, with_analysis, progress,
        )
        return {"insights_id": save_insights(record)}

    scope = search["channels"][request.channel_id]["channel_name"] if request.channel_id else search["keyword"]
    return jobs.submit("youtube", f"Audience insights: {scope}", run).to_dict()


@router.get("/insights")
def get_insights_runs(search_id: Optional[str] = None) -> List[Dict]:
    """Saved Audience Insights runs, newest first."""
    return list_insights(search_id)


@router.get("/insights/{insights_id}")
def get_insights(insights_id: str) -> Dict:
    try:
        return insights_view(load_insights(insights_id))
    except KeyError as exc:
        raise HTTPException(404, f"no saved insights {insights_id!r}") from exc
