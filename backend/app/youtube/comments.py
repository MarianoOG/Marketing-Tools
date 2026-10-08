"""Choosing videos, budgeting quota and tokens for Audience Insights.

Pure functions - no API calls, no I/O - so the estimate the UI shows before a
run is computed by exactly the code the run itself uses.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from app.youtube.config import (
    COMMENTS_PAGE_SIZE,
    EST_OUTPUT_TOKENS,
    EST_TOKENS_PER_COMMENT,
    INSIGHTS_PRICE_PER_M,
    INSIGHTS_TOKEN_BUDGET,
    MAX_VIDEOS_PER_CHANNEL,
)

_VIDEO_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{11})")


def video_id_from_url(url: str) -> Optional[str]:
    """The id in a stored ``youtube.com/watch?v=<id>`` url, for searches saved
    before videos carried a ``video_id`` field."""
    match = _VIDEO_ID_RE.search(url or "")
    return match.group(1) if match else None


def select_videos(
    channels: Dict[str, Dict],
    n: int,
    channel_id: Optional[str] = None,
    per_channel: int = MAX_VIDEOS_PER_CHANNEL,
) -> List[Dict]:
    """The ``n`` most-commented videos of a search, or of one creator in it.

    Videos without comments are skipped. Across a whole search no channel gets
    more than ``per_channel`` videos, so one big creator cannot drown the niche.
    """
    if channel_id is not None:
        scoped = {channel_id: channels[channel_id]} if channel_id in channels else {}
        per_channel = n
    else:
        scoped = channels

    candidates = []
    for cid, channel in scoped.items():
        ranked = sorted(channel.get("videos", []), key=lambda v: v.get("comment_count", 0), reverse=True)
        kept = 0
        for video in ranked:
            if kept >= per_channel or not video.get("comment_count"):
                break
            video_id = video.get("video_id") or video_id_from_url(video.get("url", ""))
            if not video_id:
                continue
            candidates.append({
                "video_id": video_id,
                "title": video.get("title", ""),
                "url": f"https://youtube.com/watch?v={video_id}",
                "channel_id": cid,
                "channel_name": channel.get("channel_name", ""),
                "comment_count": video["comment_count"],
            })
            kept += 1

    candidates.sort(key=lambda v: v["comment_count"], reverse=True)
    return candidates[:n]


def estimate_quota(videos: List[Dict], per_video: int) -> int:
    """Upper bound on quota units: one ``commentThreads.list`` page per 100 comments."""
    return sum(math.ceil(min(per_video, v["comment_count"]) / COMMENTS_PAGE_SIZE) for v in videos)


def estimate_tokens(text: str) -> int:
    """Rough token count (~4 characters per token) - good enough for a budget."""
    return len(text) // 4 + 1


def estimate_run(videos: List[Dict], per_video: int) -> Dict:
    """What a run will cost before anything is fetched."""
    expected_comments = sum(min(per_video, v["comment_count"]) for v in videos)
    input_tokens = min(expected_comments * EST_TOKENS_PER_COMMENT, INSIGHTS_TOKEN_BUDGET)
    price_in, price_out = INSIGHTS_PRICE_PER_M
    cost = (input_tokens * price_in + EST_OUTPUT_TOKENS * price_out) / 1_000_000
    return {
        "videos": videos,
        "quota_units": estimate_quota(videos, per_video),
        "expected_comments": expected_comments,
        "input_tokens": input_tokens,
        "output_tokens": EST_OUTPUT_TOKENS,
        "cost_usd": round(cost, 4),
    }


def fit_to_budget(comments: List[Dict], max_tokens: int = INSIGHTS_TOKEN_BUDGET) -> List[Dict]:
    """The most-liked comments that fit in ``max_tokens``, most-liked first."""
    kept, used = [], 0
    for comment in sorted(comments, key=lambda c: c["likes"], reverse=True):
        cost = estimate_tokens(comment["text"]) + 8  # label and like count
        if used + cost > max_tokens:
            break
        kept.append(comment)
        used += cost
    return kept


def format_for_prompt(videos: List[Dict], comments: List[Dict]) -> tuple[str, Dict[str, str]]:
    """Comments grouped under short video labels (``v1``, ``v2``...).

    Returns the prompt text and the label -> video id map to translate the
    model's answer back.
    """
    labels = {video["video_id"]: f"v{i}" for i, video in enumerate(videos, start=1)}
    by_video: Dict[str, List[Dict]] = {}
    for comment in comments:
        by_video.setdefault(comment["video_id"], []).append(comment)

    sections = []
    for video in videos:
        group = by_video.get(video["video_id"])
        if not group:
            continue
        lines = [f"## [{labels[video['video_id']]}] {video['title']} ({video['channel_name']})"]
        lines += [f"- ({c['likes']} likes) {' '.join(c['text'].split())}" for c in group]
        sections.append("\n".join(lines))
    return "\n\n".join(sections), {label: vid for vid, label in labels.items()}
