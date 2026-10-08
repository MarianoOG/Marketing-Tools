"""Creator Discovery - search YouTube, then filter, sort and inspect the result.

A search runs as a background job (it pages through up to a thousand results)
and is saved to disk when it lands; filtering and sorting a saved search is
free, so the Results page can re-ask on every widget change.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import jobs
from app.youtube.config import ACTIVITY_PRESETS, SUBSCRIBER_PRESETS, VIEW_PRESETS
from app.youtube.filters import filter_channels
from app.youtube.pipeline import search_creators
from app.youtube.presenters import channel_view, upload_pattern
from app.youtube.sorting import SORT_OPTIONS, sort_channels
from app.youtube.store import list_searches, load_search, save_search
from app.youtube.youtube_api import YouTubeService

router = APIRouter(prefix="/youtube", tags=["youtube"])


class SearchRequest(BaseModel):
    keyword: str


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
