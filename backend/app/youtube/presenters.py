"""Shape channel data for display, so the frontend only lays it out.

Everything here is derived from metrics the pipeline already computed: the
human-readable labels and the two engagement ratios the creator page shows.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List

from app.youtube.config import INSIGHT_CATEGORIES
from app.youtube.metrics import (
    format_duration,
    format_publish_interval,
    get_score_label,
    get_views_to_subs_label,
)

_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def channel_view(channel: Dict) -> Dict:
    """One channel plus its display labels."""
    median_views = channel.get('median_views', 0)
    median_likes = channel.get('median_likes', 0)
    median_comments = channel.get('median_comments', 0)
    last_published = channel.get('last_published')
    return {
        **channel,
        'publish_interval_label': format_publish_interval(channel.get('publish_interval_days')),
        'avg_duration_label': format_duration(channel.get('avg_duration', 0)),
        'score_label': get_score_label(channel.get('channel_score', 0)),
        'views_to_subs_label': get_views_to_subs_label(channel.get('views_to_subs_ratio', 0)),
        'likes_to_views_ratio': (median_likes / median_views * 100) if median_views > 0 else 0,
        'comments_to_views_ratio': (median_comments / median_views * 100) if median_views > 0 else 0,
        'days_since_last_published': (
            (datetime.now(timezone.utc) - last_published).days if last_published else None
        ),
    }


def upload_pattern(videos: List[Dict]) -> List[Dict]:
    """Uploads per month over the last six months, oldest month first."""
    month_counts = Counter()
    for video in videos:
        published_at = video.get('published_at')
        if published_at:
            month_counts[published_at.strftime('%b')] += 1
    if not month_counts:
        return []

    current_month = datetime.now().month
    last_6_months = [_MONTHS[(current_month - i - 1) % 12] for i in range(5, -1, -1)]
    return [{'month': month, 'uploads': month_counts.get(month, 0)} for month in last_6_months]


def insights_view(record: Dict) -> Dict:
    """A saved Audience Insights run, laid out for the page and the Markdown download.

    Themes are grouped by category in display order, each with links to its
    source videos, and every comment carries its video's title and link.
    """
    videos = {video['video_id']: video for video in record['videos']}
    groups = []
    if record['insights']:
        for category, label in INSIGHT_CATEGORIES.items():
            themes = [
                {**theme, 'videos': [videos[v] for v in theme['videos'] if v in videos]}
                for theme in record['insights']['themes']
                if theme['category'] == category
            ]
            if themes:
                groups.append({'category': category, 'label': label, 'themes': themes})
    comments = [
        {
            **comment,
            'video_title': videos.get(comment['video_id'], {}).get('title', ''),
            'video_url': f"https://youtube.com/watch?v={comment['video_id']}",
        }
        for comment in record['comments']
    ]
    view = {
        **record,
        'scope_label': record['channel_name'] or f'All creators for "{record["keyword"]}"',
        'ideas': record['insights']['ideas'] if record['insights'] else [],
        'theme_groups': groups,
        'comments': comments,
    }
    view['markdown'] = insights_markdown(view)
    return view


def insights_markdown(view: Dict) -> str:
    """The insights as a Markdown document."""
    lines = [
        f"# Audience insights: {view['scope_label']}",
        "",
        f"{len(view['comments'])} comments from {len(view['videos'])} videos, "
        f"{view['created_at'][:10]}.",
    ]
    if view['note']:
        lines += ["", f"> {view['note']}"]
    if view['ideas']:
        lines += ["", "## Content ideas"]
        for i, idea in enumerate(view['ideas'], start=1):
            lines += [
                "",
                f"### {i}. {idea['title']}",
                "",
                f"**Angle:** {idea['angle']}",
                "",
                f"**Answers:** {', '.join(idea['themes'])}",
                "",
                f"**Why it should work:** {idea['evidence']}",
            ]
    for group in view['theme_groups']:
        lines += ["", f"## {group['label']}"]
        for theme in group['themes']:
            lines += ["", f"### {theme['label']}", "", theme['summary'], ""]
            lines += [f"> {quote}" for quote in theme['quotes']]
            if theme['videos']:
                lines += [""] + [f"- [{v['title']}]({v['url']})" for v in theme['videos']]
    lines += ["", "## Source videos", ""]
    lines += [
        f"- [{v['title']}]({v['url']}) - {v['channel_name']} ({v['fetched']} comments, {v['status']})"
        for v in view['videos']
    ]
    return "\n".join(lines) + "\n"
