"""
Metrics Calculations and Formatters

Functions for calculating channel and video metrics,
and formatting them for human-readable display.
"""

import re
from datetime import datetime
from typing import Dict, Optional


# ============================================================================
# DURATION PARSING & FORMATTING
# ============================================================================

def parse_iso8601_duration(duration: str) -> int:
    """
    Parse ISO 8601 duration (PT1H23M45S) to seconds.

    Args:
        duration: ISO 8601 duration string

    Returns:
        Duration in seconds
    """
    if not duration:
        return 0

    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    if not match:
        return 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * 3600 + minutes * 60 + seconds


def format_duration(seconds: int) -> str:
    """
    Format seconds as HH:MM:SS or MM:SS.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string
    """
    if seconds <= 0:
        return "0:00"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# ============================================================================
# VIEW METRICS
# ============================================================================

def calculate_average_views(channel_data: Dict) -> float:
    """
    Calculate average views for a channel's videos.

    Args:
        channel_data: Channel dict with videos list

    Returns:
        Average view count across all videos
    """
    videos = channel_data.get('videos', [])
    if not videos:
        return 0.0
    return sum(v['views'] for v in videos) / len(videos)


def calculate_median_views(channel_data: Dict) -> int:
    """
    Calculate median views for a channel's videos.

    Median is more accurate than average - not skewed by viral outliers.

    Args:
        channel_data: Channel dict with videos list

    Returns:
        Median view count across all videos
    """
    videos = channel_data.get('videos', [])
    if not videos:
        return 0

    views = sorted(v['views'] for v in videos)
    mid = len(views) // 2

    if len(views) % 2 == 0:
        return (views[mid - 1] + views[mid]) // 2
    return views[mid]


# ============================================================================
# ENGAGEMENT METRICS
# ============================================================================

def calculate_median_likes(channel_data: Dict) -> int:
    """
    Calculate median likes across videos.

    Args:
        channel_data: Channel dict with videos list

    Returns:
        Median like count
    """
    videos = channel_data.get('videos', [])
    if not videos:
        return 0

    likes = sorted(v.get('likes', 0) for v in videos)
    mid = len(likes) // 2

    if len(likes) % 2 == 0:
        return (likes[mid - 1] + likes[mid]) // 2
    return likes[mid]


def calculate_median_comments(channel_data: Dict) -> int:
    """
    Calculate median comments across videos.

    Args:
        channel_data: Channel dict with videos list

    Returns:
        Median comment count
    """
    videos = channel_data.get('videos', [])
    if not videos:
        return 0

    comments = sorted(v.get('comment_count', 0) for v in videos)
    mid = len(comments) // 2

    if len(comments) % 2 == 0:
        return (comments[mid - 1] + comments[mid]) // 2
    return comments[mid]


def calculate_avg_duration(channel_data: Dict) -> int:
    """
    Calculate average video duration in seconds.

    Args:
        channel_data: Channel dict with videos list

    Returns:
        Average duration in seconds
    """
    videos = channel_data.get('videos', [])
    durations = [v.get('duration_seconds', 0) for v in videos if v.get('duration_seconds', 0) > 0]

    if not durations:
        return 0
    return sum(durations) // len(durations)


# ============================================================================
# PERFORMANCE METRICS
# ============================================================================

def calculate_views_to_subs_ratio(channel_data: Dict) -> float:
    """
    Calculate views-to-subscribers ratio as percentage.

    Args:
        channel_data: Channel dict with median_views and subscriber_count

    Returns:
        Ratio as percentage
    """
    median_views = channel_data.get('median_views', 0)
    subscribers = channel_data.get('subscriber_count', 1)

    if subscribers == 0:
        return 0.0

    return (median_views / subscribers) * 100


def get_views_to_subs_label(ratio: float) -> str:
    """
    Get performance label based on views-to-subs ratio.

    Args:
        ratio: Views-to-subscribers ratio as percentage

    Returns:
        Performance label string
    """
    if ratio < 5:
        return "Poor"
    elif ratio < 10:
        return "Below Average"
    elif ratio < 20:
        return "Average"
    elif ratio < 50:
        return "Good"
    else:
        return "Excellent"


# ============================================================================
# ACTIVITY METRICS
# ============================================================================

def calculate_publish_interval(channel_data: Dict) -> Optional[float]:
    """
    Calculate average days between video uploads.

    Args:
        channel_data: Channel dict with videos list containing published_at

    Returns:
        Average days between uploads, or None if fewer than 2 videos with dates
    """
    videos = channel_data.get('videos', [])
    dates = sorted(
        [v['published_at'] for v in videos if v.get('published_at')],
        reverse=True
    )

    if len(dates) < 2:
        return None

    intervals = [
        (dates[i] - dates[i + 1]).days
        for i in range(len(dates) - 1)
    ]
    return sum(intervals) / len(intervals) if intervals else None


def get_last_published(channel_data: Dict) -> Optional[datetime]:
    """
    Get the most recent publish date from videos.

    Args:
        channel_data: Channel dict with videos list containing published_at

    Returns:
        Most recent publish date, or None if no dates available
    """
    videos = channel_data.get('videos', [])
    dates = [v['published_at'] for v in videos if v.get('published_at')]
    return max(dates) if dates else None


def format_publish_interval(days: Optional[float]) -> str:
    """
    Format publish interval as human-readable string.

    Args:
        days: Average days between uploads

    Returns:
        Human-readable string like "Every 2 weeks" or "N/A"
    """
    if days is None:
        return "N/A"

    if days < 1:
        return "Multiple per day"
    elif days < 2:
        return "Daily"
    elif days < 4:
        return "Every few days"
    elif days < 8:
        return "Weekly"
    elif days < 15:
        return "Every 2 weeks"
    elif days < 22:
        return "Every 3 weeks"
    elif days < 45:
        return "Monthly"
    elif days < 75:
        return "Every 2 months"
    else:
        return "Infrequent"


# ============================================================================
# CHANNEL SCORE
# ============================================================================

def calculate_channel_score(channel_data: Dict) -> int:
    """
    Calculate overall channel score (0-100).

    Formula:
    - Activity (30%): Based on publish frequency
    - Content Performance (35%): Views-to-subs ratio
    - Engagement (35%): Likes and comments relative to views

    Args:
        channel_data: Channel dict with all metrics

    Returns:
        Score from 0-100
    """
    # Activity Score (0-100)
    interval_days = channel_data.get('publish_interval_days')
    if interval_days is None or interval_days > 60:
        activity_score = 30
    elif interval_days > 30:
        activity_score = 50
    elif interval_days > 14:
        activity_score = 70
    elif interval_days > 7:
        activity_score = 85
    else:
        activity_score = 100

    # Content Performance Score (0-100)
    views_to_subs = calculate_views_to_subs_ratio(channel_data)
    if views_to_subs < 2:
        perf_score = 20
    elif views_to_subs < 5:
        perf_score = 40
    elif views_to_subs < 10:
        perf_score = 60
    elif views_to_subs < 20:
        perf_score = 80
    else:
        perf_score = 100

    # Engagement Score (0-100)
    median_views = channel_data.get('median_views', 1)
    median_likes = channel_data.get('median_likes', 0)
    median_comments = channel_data.get('median_comments', 0)

    if median_views > 0:
        like_ratio = (median_likes / median_views) * 100
        comment_ratio = (median_comments / median_views) * 100
    else:
        like_ratio = 0
        comment_ratio = 0

    # Typical good engagement: 4% likes, 0.5% comments
    like_score = min(100, (like_ratio / 4) * 100)
    comment_score = min(100, (comment_ratio / 0.5) * 100)
    engagement_score = (like_score * 0.7 + comment_score * 0.3)

    # Weighted total
    total = (
        activity_score * 0.30 +
        perf_score * 0.35 +
        engagement_score * 0.35
    )

    return round(total)


def get_score_label(score: int) -> str:
    """
    Get label for channel score.

    Args:
        score: Channel score (0-100)

    Returns:
        Label string
    """
    if score >= 80:
        return "Excellent"
    elif score >= 60:
        return "Good"
    elif score >= 40:
        return "Average"
    else:
        return "Poor"
