"""
YouTube API Client

Service class for interacting with the YouTube Data API v3.
Handles video search, statistics fetching, and channel data retrieval.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.youtube.config import BATCH_SIZE, COMMENTS_PAGE_SIZE, MAX_RESULTS_PER_KEYWORD

logger = logging.getLogger(__name__)


class CommentsDisabled(Exception):
    """The video has comments turned off (HTTP 403 ``commentsDisabled``)."""


class QuotaExceeded(Exception):
    """The API key has no quota left today. Every further call would fail too."""


def _error_reason(error: HttpError) -> str:
    """The machine-readable reason of an API error, e.g. ``commentsDisabled``."""
    details = getattr(error, 'error_details', None)
    if isinstance(details, list) and details and isinstance(details[0], dict):
        return details[0].get('reason', '')
    return ''


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
                    part='statistics,snippet,contentDetails',
                    id=','.join(batch)
                )
                response = request.execute()

                for item in response.get('items', []):
                    video_id = item['id']
                    statistics = item.get('statistics', {})
                    view_count = int(statistics.get('viewCount', 0))
                    like_count = int(statistics.get('likeCount', 0))
                    comment_count = int(statistics.get('commentCount', 0))
                    published_at_str = item.get('snippet', {}).get('publishedAt', '')
                    duration = item.get('contentDetails', {}).get('duration', '')

                    # Parse ISO 8601 date
                    published_at = None
                    if published_at_str:
                        try:
                            published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                        except ValueError:
                            pass

                    stats[video_id] = {
                        'viewCount': view_count,
                        'publishedAt': published_at,
                        'likeCount': like_count,
                        'commentCount': comment_count,
                        'duration': duration,
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
                        'description': snippet.get('description', ''),
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

    def get_video_comments(self, video_id: str, max_comments: int = 200) -> List[Dict]:
        """
        Fetch the top-level comments of one video, most relevant first.

        Uses ``commentThreads.list`` only (1 quota unit per page of up to 100).
        Replies are not fetched.

        Args:
            video_id: The video to read
            max_comments: Stop after this many comments (default 200)

        Returns:
            List of comment dicts with video_id, author, text, likes, replies, published_at

        Raises:
            CommentsDisabled: The video has comments turned off
            QuotaExceeded: The daily quota is spent
        """
        comments = []
        next_page_token = None

        try:
            while len(comments) < max_comments:
                request = self._youtube.commentThreads().list(
                    part='snippet',
                    videoId=video_id,
                    maxResults=COMMENTS_PAGE_SIZE,
                    order='relevance',
                    textFormat='plainText',
                    pageToken=next_page_token,
                )
                response = request.execute()

                for item in response.get('items', []):
                    if len(comments) >= max_comments:
                        break
                    snippet = item.get('snippet', {})
                    top = snippet.get('topLevelComment', {}).get('snippet', {})
                    comments.append({
                        'video_id': video_id,
                        'author': top.get('authorDisplayName', ''),
                        'text': top.get('textDisplay', ''),
                        'likes': int(top.get('likeCount', 0)),
                        'replies': int(snippet.get('totalReplyCount', 0)),
                        'published_at': top.get('publishedAt', ''),
                    })

                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break

                # Be respectful with API calls
                time.sleep(0.1)

            return comments

        except HttpError as e:
            reason = _error_reason(e)
            if reason == 'commentsDisabled':
                logger.info(f"Comments are disabled on video {video_id}, skipping")
                raise CommentsDisabled(video_id) from e
            if reason in ('quotaExceeded', 'dailyLimitExceeded'):
                raise QuotaExceeded(str(e)) from e
            logger.warning(f"Error fetching comments for video {video_id}: {e}")
            return comments
