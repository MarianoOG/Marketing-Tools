"""
Creator Discovery Service

A service for finding and analyzing YouTube creators.
Provides search, filtering, metrics calculation, and export functionality.

Usage:
    from youtube import YouTubeService, search_creators, SearchError

    service = YouTubeService(api_key)
    channels = search_creators(
        service=service,
        keyword="tech reviews",
        view_range=(1000, 100000),
        subscriber_range=(1000, 100000),
    )
"""

# Configuration and presets
from config import (
    ACTIVITY_PRESETS,
    BATCH_SIZE,
    MAX_CHANNEL_VIDEOS,
    MAX_RESULTS_PER_KEYWORD,
    MAX_SUBSCRIBERS,
    MAX_VIEWS,
    MIN_CHANNEL_VIDEOS,
    MIN_SUBSCRIBERS,
    MIN_VIEWS,
    OUTPUT_FILE,
    SUBSCRIBER_PRESETS,
    VIEW_PRESETS,
)

# YouTube API client
from youtube_api import YouTubeService

# Filtering functions
from filters import (
    filter_channels_by_activity,
    filter_channels_by_subscribers,
    filter_channels_by_video_count,
    filter_videos_by_views,
)

# Sorting
from sorting import SORT_OPTIONS, SortOption, sort_channels

# Metrics and formatters
from metrics import (
    calculate_average_views,
    calculate_avg_duration,
    calculate_channel_score,
    calculate_median_comments,
    calculate_median_likes,
    calculate_median_views,
    calculate_publish_interval,
    calculate_views_to_subs_ratio,
    format_duration,
    format_publish_interval,
    get_last_published,
    get_score_label,
    get_views_to_subs_label,
    parse_iso8601_duration,
)

# Aggregation and export
from aggregation import aggregate_channels, merge_channels, write_channels_to_jsonl

# Search pipeline
from pipeline import SearchError, search_creators

__all__ = [
    # Config
    "ACTIVITY_PRESETS",
    "BATCH_SIZE",
    "MAX_CHANNEL_VIDEOS",
    "MAX_RESULTS_PER_KEYWORD",
    "MAX_SUBSCRIBERS",
    "MAX_VIEWS",
    "MIN_CHANNEL_VIDEOS",
    "MIN_SUBSCRIBERS",
    "MIN_VIEWS",
    "OUTPUT_FILE",
    "SUBSCRIBER_PRESETS",
    "VIEW_PRESETS",
    # API
    "YouTubeService",
    # Filters
    "filter_channels_by_activity",
    "filter_channels_by_subscribers",
    "filter_channels_by_video_count",
    "filter_videos_by_views",
    # Sorting
    "SORT_OPTIONS",
    "SortOption",
    "sort_channels",
    # Metrics
    "calculate_average_views",
    "calculate_avg_duration",
    "calculate_channel_score",
    "calculate_median_comments",
    "calculate_median_likes",
    "calculate_median_views",
    "calculate_publish_interval",
    "calculate_views_to_subs_ratio",
    "format_duration",
    "format_publish_interval",
    "get_last_published",
    "get_score_label",
    "get_views_to_subs_label",
    "parse_iso8601_duration",
    # Aggregation
    "aggregate_channels",
    "merge_channels",
    "write_channels_to_jsonl",
    # Pipeline
    "SearchError",
    "search_creators",
]
