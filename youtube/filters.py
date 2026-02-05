"""
Filtering Functions

Functions to filter videos and channels by various criteria
such as view count, subscriber count, video count, and activity.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from metrics import parse_iso8601_duration


def filter_videos_by_views(videos: List[Dict], stats: Dict[str, Dict], min_views: int, max_views: int) -> List[Dict]:
    """
    Filter videos to only those with view counts between min_views and max_views.

    Args:
        videos: List of video dicts with video_id
        stats: Dict mapping video_id to stats
        min_views: Minimum view count threshold
        max_views: Maximum view count threshold

    Returns:
        Filtered list of videos with their view counts and publish dates
    """
    filtered = []
    for video in videos:
        video_id = video['video_id']
        if video_id not in stats:
            continue

        video_stats = stats[video_id]
        view_count = video_stats['viewCount']
        if min_views <= view_count <= max_views:
            filtered.append({
                **video,
                'views': view_count,
                'published_at': video_stats.get('publishedAt'),
                'likes': video_stats.get('likeCount', 0),
                'comment_count': video_stats.get('commentCount', 0),
                'duration_seconds': parse_iso8601_duration(video_stats.get('duration', '')),
            })

    return filtered


def filter_channels_by_video_count(channel_ids: List[str], stats: Dict[str, Dict], min_videos: int, max_videos: int) -> List[str]:
    """
    Filter channels to only those with video counts between min_videos and max_videos.

    Args:
        channel_ids: List of channel IDs
        stats: Dict mapping channel_id to stats
        min_videos: Minimum number of videos threshold
        max_videos: Maximum number of videos threshold

    Returns:
        Filtered list of channel IDs that meet the criteria
    """
    filtered = []
    for channel_id in channel_ids:
        if channel_id not in stats:
            continue

        video_count = stats[channel_id]['videoCount']
        if min_videos <= video_count <= max_videos:
            filtered.append(channel_id)

    return filtered


def filter_channels_by_subscribers(channel_ids: List[str], stats: Dict[str, Dict], min_subscribers: int, max_subscribers: int) -> List[str]:
    """
    Filter channels to only those with subscriber counts between min_subscribers and max_subscribers.

    Args:
        channel_ids: List of channel IDs
        stats: Dict mapping channel_id to stats
        min_subscribers: Minimum subscriber count threshold
        max_subscribers: Maximum subscriber count threshold

    Returns:
        Filtered list of channel IDs that meet the criteria
    """
    filtered = []
    for channel_id in channel_ids:
        if channel_id not in stats:
            continue

        subscriber_count = stats[channel_id]['subscriberCount']
        if min_subscribers <= subscriber_count <= max_subscribers:
            filtered.append(channel_id)

    return filtered


def filter_channels_by_activity(channels: Dict[str, Dict], max_days_since_publish: int = 30) -> Dict[str, Dict]:
    """
    Filter to channels that have been active within N days.

    Args:
        channels: Dict mapping channel_id to channel data
        max_days_since_publish: Maximum days since last video upload

    Returns:
        Filtered dict of channels active within the timeframe
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days_since_publish)

    return {
        cid: data for cid, data in channels.items()
        if data.get('last_published') and data['last_published'] >= cutoff
    }
