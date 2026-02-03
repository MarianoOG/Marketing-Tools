"""
Creator Discovery Service
Business logic for finding and filtering YouTube creators.

This module provides core functionality for:
- Searching YouTube for videos by keyword
- Fetching video and channel statistics
- Filtering videos and channels by various criteria
- Calculating activity metrics (median views, publish interval)
- Aggregating results by channel
- Exporting results to JSONL format
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ============================================================================
# CONFIGURATION
# ============================================================================

# Global configuration - easy to modify
MAX_RESULTS_PER_KEYWORD = 1000
OUTPUT_FILE = "creators.jsonl"
MIN_VIEWS = 100
MAX_VIEWS = 1000
MIN_CHANNEL_VIDEOS = 5
MAX_CHANNEL_VIDEOS = 100
MIN_SUBSCRIBERS = 100
MAX_SUBSCRIBERS = 10000
BATCH_SIZE = 50  # Max channel IDs per batch request

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# YOUTUBE SERVICE CLASS
# ============================================================================

class YouTubeService:
    """Service class for interacting with YouTube Data API v3."""

    def __init__(self, api_key: str):
        """
        Initialize YouTube API client.

        Args:
            api_key: YouTube Data API v3 key

        Raises:
            ValueError: If api_key is empty or None
        """
        if not api_key:
            raise ValueError("API key is required")

        self._youtube = build('youtube', 'v3', developerKey=api_key)
        logger.info("YouTube service initialized successfully")

    def search_videos(self, keyword: str, max_results: int = 50, max_total_results: Optional[int] = None) -> List[Dict]:
        """
        Search YouTube for videos matching a keyword.

        Args:
            keyword: Search keyword
            max_results: Max results per API call (YouTube API max is 50)
            max_total_results: Total max results to collect (defaults to MAX_RESULTS_PER_KEYWORD)

        Returns:
            List of video dictionaries with video_id, title, channel_id, channel_name
        """
        if max_total_results is None:
            max_total_results = MAX_RESULTS_PER_KEYWORD

        all_videos = []
        next_page_token = None

        try:
            while len(all_videos) < max_total_results:
                request = self._youtube.search().list(
                    q=keyword,
                    part='id,snippet',
                    type='video',
                    maxResults=min(max_results, max_total_results - len(all_videos)),
                    pageToken=next_page_token,
                    order='relevance'
                )

                response = request.execute()

                for item in response.get('items', []):
                    if len(all_videos) >= max_total_results:
                        break
                    all_videos.append({
                        'video_id': item['id']['videoId'],
                        'title': item['snippet']['title'],
                        'channel_id': item['snippet']['channelId'],
                        'channel_name': item['snippet']['channelTitle'],
                    })

                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break

                # Be respectful with API calls
                time.sleep(0.1)

            logger.info(f"Found {len(all_videos)} videos for keyword '{keyword}'")
            return all_videos

        except HttpError as e:
            logger.warning(f"Error searching for '{keyword}': {e}")
            return []

    def get_video_statistics(self, video_ids: List[str]) -> Dict[str, Dict]:
        """
        Fetch statistics and snippet for videos (view count, publish date).

        Args:
            video_ids: List of video IDs

        Returns:
            Dict mapping video_id to stats dict with viewCount and publishedAt
        """
        stats = {}

        if not video_ids:
            return stats

        try:
            # Batch requests - max 50 video IDs per request
            for i in range(0, len(video_ids), BATCH_SIZE):
                batch = video_ids[i:i + BATCH_SIZE]

                request = self._youtube.videos().list(
                    part='statistics,snippet',
                    id=','.join(batch)
                )
                response = request.execute()

                for item in response.get('items', []):
                    video_id = item['id']
                    view_count = int(item.get('statistics', {}).get('viewCount', 0))
                    published_at_str = item.get('snippet', {}).get('publishedAt', '')

                    # Parse ISO 8601 date
                    published_at = None
                    if published_at_str:
                        try:
                            published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                        except ValueError:
                            pass

                    stats[video_id] = {
                        'viewCount': view_count,
                        'publishedAt': published_at
                    }

                # Be respectful with API calls
                time.sleep(0.1)

            return stats

        except HttpError as e:
            logger.warning(f"Error fetching video statistics: {e}")
            return stats

    def get_channel_statistics(self, channel_ids: List[str]) -> Dict[str, Dict]:
        """
        Fetch statistics for channels (subscriber count, video count, views, etc.).

        Args:
            channel_ids: List of channel IDs

        Returns:
            Dict mapping channel_id to stats dict with subscriberCount, videoCount,
            viewCount, customUrl, country, publishedAt, thumbnailUrl, uploadsPlaylistId
        """
        stats = {}

        if not channel_ids:
            return stats

        try:
            # Batch requests - max 50 channel IDs per request
            for i in range(0, len(channel_ids), BATCH_SIZE):
                batch = channel_ids[i:i + BATCH_SIZE]

                request = self._youtube.channels().list(
                    part='statistics,snippet,contentDetails',
                    id=','.join(batch)
                )
                response = request.execute()

                for item in response.get('items', []):
                    channel_id = item['id']
                    snippet = item.get('snippet', {})
                    statistics = item.get('statistics', {})
                    content_details = item.get('contentDetails', {})

                    stats[channel_id] = {
                        'subscriberCount': int(statistics.get('subscriberCount', 0)),
                        'videoCount': int(statistics.get('videoCount', 0)),
                        'viewCount': int(statistics.get('viewCount', 0)),
                        'customUrl': snippet.get('customUrl', ''),
                        'country': snippet.get('country', ''),
                        'publishedAt': snippet.get('publishedAt', ''),
                        'thumbnailUrl': snippet.get('thumbnails', {}).get('medium', {}).get('url', ''),
                        'uploadsPlaylistId': content_details.get('relatedPlaylists', {}).get('uploads', ''),
                    }

                # Be respectful with API calls
                time.sleep(0.1)

            return stats

        except HttpError as e:
            logger.warning(f"Error fetching channel statistics: {e}")
            return stats

    def get_channel_latest_videos(self, uploads_playlist_id: str, max_results: int = 10) -> List[Dict]:
        """
        Fetch the latest videos from a channel's uploads playlist.

        Args:
            uploads_playlist_id: The playlist ID for the channel's uploads
            max_results: Maximum number of videos to fetch (default 10)

        Returns:
            List of video dictionaries with video_id, title, views, published_at, url
        """
        if not uploads_playlist_id:
            return []

        videos = []

        try:
            # Step 1: Get playlist items (video IDs and basic info)
            request = self._youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=max_results
            )
            response = request.execute()

            video_ids = []
            video_info = {}

            for item in response.get('items', []):
                snippet = item.get('snippet', {})
                video_id = snippet.get('resourceId', {}).get('videoId', '')
                if video_id:
                    video_ids.append(video_id)
                    video_info[video_id] = {
                        'video_id': video_id,
                        'title': snippet.get('title', ''),
                        'published_at_str': snippet.get('publishedAt', ''),
                    }

            # Step 2: Get video statistics for view counts
            if video_ids:
                stats = self.get_video_statistics(video_ids)

                for video_id in video_ids:
                    info = video_info[video_id]
                    video_stats = stats.get(video_id, {})

                    # Parse the published date
                    published_at = None
                    if info['published_at_str']:
                        try:
                            published_at = datetime.fromisoformat(
                                info['published_at_str'].replace('Z', '+00:00')
                            )
                        except ValueError:
                            pass

                    videos.append({
                        'video_id': video_id,
                        'title': info['title'],
                        'views': video_stats.get('viewCount', 0),
                        'published_at': published_at or video_stats.get('publishedAt'),
                        'url': f"youtube.com/watch?v={video_id}",
                    })

            return videos

        except HttpError as e:
            logger.warning(f"Error fetching playlist videos: {e}")
            return []

# ============================================================================
# FILTERING & VALIDATION
# ============================================================================

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
                'published_at': video_stats.get('publishedAt')
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
    from datetime import timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days_since_publish)

    return {
        cid: data for cid, data in channels.items()
        if data.get('last_published') and data['last_published'] >= cutoff
    }


# ============================================================================
# SORTING
# ============================================================================

class SortOption:
    """Sort options for channel results."""
    RELEVANCE = "relevance"
    MEDIAN_VIEWS = "median_views"
    SUBSCRIBERS = "subscribers"
    ACTIVITY = "activity"


def sort_channels(channels: Dict[str, Dict], sort_by: str, descending: bool = True) -> List[Dict]:
    """
    Sort channels by specified criteria.

    Args:
        channels: Dict mapping channel_id to channel data
        sort_by: One of SortOption values
        descending: Sort in descending order (default True)

    Returns:
        List of channel data dicts (not dict) to preserve sort order
    """
    channel_list = list(channels.values())

    if sort_by == SortOption.RELEVANCE:
        return channel_list

    key_funcs = {
        SortOption.MEDIAN_VIEWS: lambda c: c.get('median_views', 0),
        SortOption.SUBSCRIBERS: lambda c: c.get('subscriber_count', 0),
        SortOption.ACTIVITY: lambda c: c.get('last_published') or datetime.min,
    }

    key_func = key_funcs.get(sort_by)
    if key_func is None:
        return channel_list

    # For activity, we want most recent first when descending
    # Handle timezone-naive datetime.min comparison
    if sort_by == SortOption.ACTIVITY:
        def activity_key(c):
            lp = c.get('last_published')
            if lp is None:
                return datetime.min
            # Make timezone-naive for comparison
            if lp.tzinfo is not None:
                return lp.replace(tzinfo=None)
            return lp
        key_func = activity_key

    return sorted(channel_list, key=key_func, reverse=descending)

# ============================================================================
# DATA AGGREGATION
# ============================================================================

def aggregate_channels(videos: List[Dict], channel_stats: Dict[str, Dict], keyword: str) -> Dict[str, Dict]:
    """
    Aggregate videos by channel and add channel metadata.

    Args:
        videos: List of filtered videos with views and published_at
        channel_stats: Dict mapping channel_id to stats
        keyword: The keyword that found these videos

    Returns:
        Dict mapping channel_id to channel data with videos list and calculated metrics
    """
    channels = {}

    for video in videos:
        channel_id = video['channel_id']

        if channel_id not in channel_stats:
            continue

        if channel_id not in channels:
            # Create new channel entry
            stats = channel_stats[channel_id]

            # Parse creation date
            created_at = None
            published_at_str = stats.get('publishedAt', '')
            if published_at_str:
                try:
                    created_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                except ValueError:
                    pass

            channels[channel_id] = {
                'channel_name': video['channel_name'],
                'channel_id': channel_id,
                'channel_url': f"youtube.com/channel/{channel_id}",
                'subscriber_count': stats['subscriberCount'],
                'total_videos': stats['videoCount'],
                'total_channel_views': stats.get('viewCount', 0),
                'country': stats.get('country', ''),
                'created_at': created_at,
                'thumbnail_url': stats.get('thumbnailUrl', ''),
                'uploads_playlist_id': stats.get('uploadsPlaylistId', ''),
                'videos': []
            }

        # Add video to channel's video list
        channels[channel_id]['videos'].append({
            'title': video['title'],
            'url': f"youtube.com/watch?v={video['video_id']}",
            'views': video['views'],
            'published_at': video.get('published_at'),
            'keywords': [keyword] if keyword not in [k for v in channels[channel_id]['videos'] for k in v.get('keywords', [])] else []
        })

    # Calculate derived metrics for each channel
    for channel_id, channel_data in channels.items():
        channel_data['median_views'] = calculate_median_views(channel_data)
        channel_data['average_views'] = calculate_average_views(channel_data)
        channel_data['publish_interval_days'] = calculate_publish_interval(channel_data)
        channel_data['last_published'] = get_last_published(channel_data)

    return channels

def merge_channels(existing_channels: Dict[str, Dict], new_channels: Dict[str, Dict]) -> Dict[str, Dict]:
    """
    Merge new channel data into existing channels, combining videos and keywords.

    Args:
        existing_channels: Dict of existing channels
        new_channels: Dict of new channels to merge

    Returns:
        Merged channel dict
    """
    merged = existing_channels.copy()

    for channel_id, new_data in new_channels.items():
        if channel_id in merged:
            # Channel already exists - merge videos
            existing_videos_ids = {v['url'] for v in merged[channel_id]['videos']}

            for new_video in new_data['videos']:
                # Check if video already exists
                if new_video['url'] not in existing_videos_ids:
                    merged[channel_id]['videos'].append(new_video)
                else:
                    # Video exists - add keyword if not already there
                    for existing_video in merged[channel_id]['videos']:
                        if existing_video['url'] == new_video['url']:
                            for keyword in new_video.get('keywords', []):
                                if keyword not in existing_video.get('keywords', []):
                                    existing_video['keywords'].append(keyword)
        else:
            # New channel - add it
            merged[channel_id] = new_data

    return merged

# ============================================================================
# OUTPUT
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

def write_channels_to_jsonl(channels: Dict[str, Dict], output_file: str):
    """
    Write aggregated channel data to JSONL file.

    Args:
        channels: Dict mapping channel_id to channel data
        output_file: Output JSONL filename
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for channel_id, channel_data in channels.items():
                # Calculate average views
                avg_views = calculate_average_views(channel_data)

                # Create output row
                output_row = {
                    'channel_name': channel_data['channel_name'],
                    'channel_id': channel_data['channel_id'],
                    'channel_url': channel_data['channel_url'],
                    'subscriber_count': channel_data['subscriber_count'],
                    'total_videos': channel_data['total_videos'],
                    'average_views': round(avg_views, 1),
                    'videos': channel_data['videos']
                }

                # Write as single line JSON
                f.write(json.dumps(output_row, ensure_ascii=False) + '\n')

        logger.info(f"Results saved to {output_file}")

    except IOError as e:
        logger.warning(f"Error writing to {output_file}: {e}")
