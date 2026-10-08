"""Audience Insights - turn a search's comments into content ideas.

A run fetches the top-level comments of the most-discussed videos, asks an LLM
for themes (questions, pain points, requests, praise) and content ideas in one
structured-output call, and returns a record the store saves. Without
``OPENAI_API_KEY`` the run still fetches and saves the comments; only the
analysis is skipped.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Literal, Optional

from openai import OpenAI
from pydantic import BaseModel

from app.youtube.comments import fit_to_budget, format_for_prompt
from app.youtube.config import INSIGHTS_MODEL
from app.youtube.youtube_api import CommentsDisabled, QuotaExceeded, YouTubeService

logger = logging.getLogger(__name__)

_client = None


def client() -> OpenAI:
    """Built on first use, so a missing key fails the analysis rather than server startup."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


class Theme(BaseModel):
    category: Literal["question", "pain_point", "request", "praise"]
    label: str
    summary: str
    quotes: List[str]
    videos: List[str]


class ContentIdea(BaseModel):
    title: str
    angle: str
    themes: List[str]
    evidence: str


class AudienceInsights(BaseModel):
    ideas: List[ContentIdea]
    themes: List[Theme]


SYSTEM_PROMPT = """You analyse YouTube comments to find content ideas for a creator \
who wants to serve this audience. The comments are grouped under video labels like [v1].

Find recurring themes, each in one category:
- question: what viewers ask and the video did not answer
- pain_point: what they complain about or find confusing
- request: what they explicitly ask to see ("can you make a video on...")
- praise: what they say already works

For each theme give a short label, a one-line summary, 2-3 quotes copied verbatim \
from the comments (in their original language, not translated) and the labels of \
the videos they come from.

Then propose content ideas that answer those themes: a working title, the angle, \
the labels of the themes it answers, and the evidence for why it should work. \
Order ideas from the strongest evidence to the weakest.

Stay grounded: only report themes that comments actually support, and never \
invent or paraphrase a quote. Write everything except the quotes in {language}."""


def analyze(videos: List[Dict], comments: List[Dict], language: str, topic: str) -> tuple[Dict, Dict]:
    """One structured-output call. Returns (insights, token usage)."""
    text, label_to_id = format_for_prompt(videos, comments)
    completion = client().chat.completions.parse(
        model=INSIGHTS_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(language=language)},
            {"role": "user", "content": f"Topic: {topic}\n\n{text}"},
        ],
        response_format=AudienceInsights,
    )
    parsed = completion.choices[0].message.parsed
    usage = completion.usage
    return (
        _ground(parsed.model_dump(), comments, label_to_id),
        {"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens} if usage else {},
    )


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def _ground(insights: Dict, comments: List[Dict], label_to_id: Dict[str, str]) -> Dict:
    """Keep only quotes that really appear in a comment, and swap video labels for ids."""
    corpus = [_normalize(c["text"]) for c in comments]
    for theme in insights["themes"]:
        theme["quotes"] = [q for q in theme["quotes"] if any(_normalize(q) in text for text in corpus)]
        theme["videos"] = [label_to_id[v.strip("[]")] for v in theme["videos"] if v.strip("[]") in label_to_id]
    return insights


def run_insights(
    service: YouTubeService,
    search: Dict,
    videos: List[Dict],
    per_video: int,
    language: str,
    channel_id: Optional[str],
    with_analysis: bool,
    on_progress: Callable[[str], None],
) -> Dict:
    """Fetch, budget and analyse. Returns the record to save."""
    comments: List[Dict] = []
    fetched = []
    for i, video in enumerate(videos, start=1):
        on_progress(f"Fetching comments {i}/{len(videos)}: {video['title']}")
        status = "ok"
        try:
            found = service.get_video_comments(video["video_id"], per_video)
        except CommentsDisabled:
            found, status = [], "comments disabled"
            on_progress(f"Comments are disabled on \"{video['title']}\" - skipped.")
        except QuotaExceeded:
            on_progress("YouTube quota exhausted - analysing what was fetched so far.")
            fetched.append({**video, "fetched": 0, "status": "quota exceeded"})
            break
        comments.extend(found)
        fetched.append({**video, "fetched": len(found), "status": status})

    on_progress(f"Fetched {len(comments)} comments.")
    insights, usage, note = None, {}, None
    if not comments:
        note = "No comments were fetched, so there is nothing to analyse."
    elif not with_analysis:
        note = "The analysis needs OPENAI_API_KEY in backend/.env. The comments are still below."
    else:
        budgeted = fit_to_budget(comments)
        if len(budgeted) < len(comments):
            on_progress(f"Kept the {len(budgeted)} most-liked comments to fit the token budget.")
        on_progress(f"Analysing {len(budgeted)} comments with {INSIGHTS_MODEL}...")
        try:
            insights, usage = analyze(fetched, budgeted, language, search["keyword"])
        except Exception as exc:  # the fetched comments are kept either way
            logger.warning(f"Audience insights analysis failed: {exc}")
            note = f"The analysis failed: {exc}. The comments are still below."

    channel = search["channels"].get(channel_id) if channel_id else None
    return {
        "search_id": search["id"],
        "keyword": search["keyword"],
        "channel_id": channel_id,
        "channel_name": channel["channel_name"] if channel else None,
        "language": language,
        "per_video": per_video,
        "model": INSIGHTS_MODEL if insights else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "videos": fetched,
        "comments": comments,
        "insights": insights,
        "usage": usage,
        "note": note,
    }
