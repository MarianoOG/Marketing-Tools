"""Saved searches - one JSON file per search under ``<DATA_DIR>/youtube/searches/``.

A search spends YouTube quota, so its result is kept rather than living only in
a browser session: a page refresh, or a search the user walked away from, can
still be reopened. The file holds the full aggregated channel data, metrics
included, so filtering and sorting it again costs no API call.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.settings import YOUTUBE_DIR

SEARCHES_DIR = YOUTUBE_DIR / "searches"

#: Search ids are generated here and are safe filenames; anything else is refused.
_ID_RE = re.compile(r"^[0-9TZ]{16}_[a-z0-9_]*$")


def _parse_datetime(value: Any) -> Any:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _decode(channels: Dict[str, Dict]) -> Dict[str, Dict]:
    """Restore the datetimes JSON flattened to strings; filters and sorts compare them."""
    for channel in channels.values():
        channel["created_at"] = _parse_datetime(channel.get("created_at"))
        channel["last_published"] = _parse_datetime(channel.get("last_published"))
        for video in channel.get("videos", []):
            video["published_at"] = _parse_datetime(video.get("published_at"))
    return channels


def _encode(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def save_search(keyword: str, channels: Dict[str, Dict]) -> str:
    """Write one search and return its id."""
    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^a-z0-9]+", "_", keyword.lower()).strip("_")[:40]
    search_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{slug}"
    SEARCHES_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "id": search_id,
        "keyword": keyword,
        "created_at": now.isoformat(),
        "channels": channels,
    }
    path = SEARCHES_DIR / f"{search_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, default=_encode), encoding="utf-8")
    return search_id


def load_search(search_id: str) -> Dict:
    """One saved search with its datetimes restored. Raises ``KeyError`` if unknown."""
    path = SEARCHES_DIR / f"{search_id}.json"
    if not _ID_RE.match(search_id) or not path.is_file():
        raise KeyError(search_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["channels"] = _decode(record["channels"])
    return record


def list_searches() -> List[Dict]:
    """Every saved search, newest first, without its channel data."""
    if not SEARCHES_DIR.is_dir():
        return []
    searches = []
    for path in sorted(SEARCHES_DIR.glob("*.json"), reverse=True):
        record = json.loads(path.read_text(encoding="utf-8"))
        searches.append(
            {
                "id": record["id"],
                "keyword": record["keyword"],
                "created_at": record["created_at"],
                "count": len(record["channels"]),
            }
        )
    return searches
