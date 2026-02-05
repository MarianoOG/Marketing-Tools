"""
Search Pipeline

High-level search orchestration that ties together all the
service components to execute a full creator search.
"""

from typing import Callable, Dict, Optional, Tuple

from aggregation import aggregate_channels, merge_channels
from filters import (
    filter_channels_by_activity,
    filter_channels_by_subscribers,
    filter_videos_by_views,
)
from youtube_api import YouTubeService


class SearchError(Exception):
    """Exception raised when search fails."""
    pass


def search_creators(
    service: YouTubeService,
    keyword: str,
    view_range: Tuple[int, int],
    subscriber_range: Tuple[int, int],
    activity_days: Optional[int] = None,
    on_progress: Optional[Callable[[str], None]] = None
) -> Dict[str, Dict]:
    """
    Execute full creator search pipeline.

    Args:
        service: YouTubeService instance
        keyword: Search keyword
        view_range: (min_views, max_views) tuple
        subscriber_range: (min_subs, max_subs) tuple
        activity_days: Filter by activity within N days (optional)
        on_progress: Callback for progress updates (optional)

    Returns:
        Dict of channel_id -> channel data

    Raises:
        SearchError: When search fails at any step
    """
    def progress(msg: str):
        if on_progress:
            on_progress(msg)

    min_views, max_views = view_range
    min_subs, max_subs = subscriber_range

    # Step 1: Search for videos
    progress("Searching for videos...")
    videos = service.search_videos(keyword)
    if not videos:
        raise SearchError(f"No videos found for '{keyword}'")
    progress(f"Found {len(videos)} videos")

    # Step 2: Get video statistics
    progress("Fetching video statistics...")
    video_ids = [v['video_id'] for v in videos]
    video_stats = service.get_video_statistics(video_ids)

    # Step 3: Filter by view count
    progress("Filtering by view count...")
    filtered_videos = filter_videos_by_views(videos, video_stats, min_views, max_views)
    if not filtered_videos:
        raise SearchError(f"No videos found with {min_views:,}-{max_views:,} views")
    progress(f"{len(filtered_videos)} videos match view criteria")

    # Step 4: Get channel statistics
    progress("Fetching channel statistics...")
    channel_ids = list(set(v['channel_id'] for v in filtered_videos))
    channel_stats = service.get_channel_statistics(channel_ids)

    # Step 5: Filter by subscriber count
    progress("Filtering by subscribers...")
    valid_channel_ids = filter_channels_by_subscribers(channel_ids, channel_stats, min_subs, max_subs)
    filtered_videos = [v for v in filtered_videos if v['channel_id'] in valid_channel_ids]

    if not filtered_videos:
        raise SearchError("No channels match subscriber criteria")

    # Step 6: Aggregate by channel
    progress("Aggregating results...")
    all_channels: Dict[str, Dict] = {}
    keyword_channels = aggregate_channels(filtered_videos, channel_stats, keyword)
    all_channels = merge_channels(all_channels, keyword_channels)

    # Step 7: Filter by activity if specified
    if activity_days:
        progress(f"Filtering by activity (last {activity_days} days)...")
        all_channels = filter_channels_by_activity(all_channels, activity_days)

    progress(f"Found {len(all_channels)} creators")

    return all_channels
