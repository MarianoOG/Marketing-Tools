"""
Data Aggregation and Export

Functions for aggregating videos by channel, merging channel data,
and exporting results to various formats.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List

from metrics import (
    calculate_average_views,
    calculate_avg_duration,
    calculate_channel_score,
    calculate_median_comments,
    calculate_median_likes,
    calculate_median_views,
    calculate_publish_interval,
    calculate_views_to_subs_ratio,
    get_last_published,
)

logger = logging.getLogger(__name__)


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
                'description': stats.get('description', ''),
                'videos': []
            }

        # Add video to channel's video list
        channels[channel_id]['videos'].append({
            'title': video['title'],
            'url': f"youtube.com/watch?v={video['video_id']}",
            'views': video['views'],
            'published_at': video.get('published_at'),
            'likes': video.get('likes', 0),
            'comment_count': video.get('comment_count', 0),
            'duration_seconds': video.get('duration_seconds', 0),
            'keywords': [keyword] if keyword not in [k for v in channels[channel_id]['videos'] for k in v.get('keywords', [])] else []
        })

    # Calculate derived metrics for each channel
    for channel_id, channel_data in channels.items():
        channel_data['median_views'] = calculate_median_views(channel_data)
        channel_data['average_views'] = calculate_average_views(channel_data)
        channel_data['publish_interval_days'] = calculate_publish_interval(channel_data)
        channel_data['last_published'] = get_last_published(channel_data)
        # New metrics
        channel_data['median_likes'] = calculate_median_likes(channel_data)
        channel_data['median_comments'] = calculate_median_comments(channel_data)
        channel_data['avg_duration'] = calculate_avg_duration(channel_data)
        channel_data['views_to_subs_ratio'] = calculate_views_to_subs_ratio(channel_data)
        channel_data['channel_score'] = calculate_channel_score(channel_data)

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
