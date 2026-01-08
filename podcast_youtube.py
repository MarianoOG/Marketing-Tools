#!/usr/bin/env python3
"""
YouTube Podcast Scraper for Guest Appearances
Finds small podcasts (100-1,000 views) suitable for guest appearances.

Installation:
    1. pip install -r requirements.txt
    2. Create a .env file in the same directory with: YOUTUBE_API_KEY=your_api_key_here
    3. Get your API key from: https://console.cloud.google.com/
    4. Run: python podcast_youtube.py

Output:
    Results are saved to podcasts.jsonl with one channel per line.
"""

import json
import os
import logging
import time
from typing import Dict, List
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
import streamlit as st

# ============================================================================
# CONFIGURATION
# ============================================================================

# Load environment variables from .env file
load_dotenv()

# Global configuration - easy to modify
MAX_RESULTS_PER_KEYWORD = 1000
OUTPUT_FILE = "podcasts.jsonl"
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
# YOUTUBE API CLIENT
# ============================================================================

def init_youtube_client():
    """Initialize YouTube API client using API key from environment."""
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        logger.error("YOUTUBE_API_KEY not found in environment. Please add it to .env file.")
        raise ValueError("YOUTUBE_API_KEY environment variable not set")

    return build('youtube', 'v3', developerKey=api_key)

youtube = None

# ============================================================================
# API CALLS
# ============================================================================

@st.cache_data(show_spinner=False)
def search_videos(keyword: str, max_results: int = 50) -> List[Dict]:
    """
    Search YouTube for videos matching a keyword.

    Args:
        youtube: YouTube API client
        keyword: Search keyword
        max_results: Max results per API call (YouTube API max is 50)

    Returns:
        List of video IDs found
    """
    global youtube
    if youtube is None:
        return []
    
    all_videos = []
    next_page_token = None

    try:
        while len(all_videos) < MAX_RESULTS_PER_KEYWORD:
            request = youtube.search().list(
                q=keyword,
                part='id,snippet',
                type='video',
                maxResults=min(max_results, MAX_RESULTS_PER_KEYWORD - len(all_videos)),
                pageToken=next_page_token,
                order='relevance'
            )

            response = request.execute()

            for item in response.get('items', []):
                if len(all_videos) >= MAX_RESULTS_PER_KEYWORD:
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

@st.cache_data(show_spinner=False)
def get_video_statistics(video_ids: List[str]) -> Dict[str, Dict]:
    """
    Fetch statistics for videos (view count).

    Args:
        youtube: YouTube API client
        video_ids: List of video IDs

    Returns:
        Dict mapping video_id to stats (viewCount)
    """
    global youtube
    if youtube is None:
        return {}
    
    stats = {}

    if not video_ids:
        return stats

    try:
        # Batch requests - max 50 video IDs per request
        for i in range(0, len(video_ids), BATCH_SIZE):
            batch = video_ids[i:i + BATCH_SIZE]

            request = youtube.videos().list(
                part='statistics',
                id=','.join(batch)
            )
            response = request.execute()

            for item in response.get('items', []):
                video_id = item['id']
                view_count = int(item.get('statistics', {}).get('viewCount', 0))
                stats[video_id] = {'viewCount': view_count}

            # Be respectful with API calls
            time.sleep(0.1)

        return stats

    except HttpError as e:
        logger.warning(f"Error fetching video statistics: {e}")
        return stats


@st.cache_data(show_spinner=False)
def get_channel_statistics(channel_ids: List[str]) -> Dict[str, Dict]:
    """
    Fetch statistics for channels (subscriber count, video count).

    Args:
        youtube: YouTube API client
        channel_ids: List of channel IDs

    Returns:
        Dict mapping channel_id to stats
    """
    global youtube
    if youtube is None:
        return {}

    stats = {}

    if not channel_ids:
        return stats

    try:
        # Batch requests - max 50 channel IDs per request
        for i in range(0, len(channel_ids), BATCH_SIZE):
            batch = channel_ids[i:i + BATCH_SIZE]

            request = youtube.channels().list(
                part='statistics,snippet',
                id=','.join(batch)
            )
            response = request.execute()

            for item in response.get('items', []):
                channel_id = item['id']
                stats[channel_id] = {
                    'subscriberCount': int(item.get('statistics', {}).get('subscriberCount', 0)),
                    'videoCount': int(item.get('statistics', {}).get('videoCount', 0)),
                    'customUrl': item.get('snippet', {}).get('customUrl', '')
                }

            # Be respectful with API calls
            time.sleep(0.1)

        return stats

    except HttpError as e:
        logger.warning(f"Error fetching channel statistics: {e}")
        return stats

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
        Filtered list of videos with their view counts
    """
    filtered = []
    for video in videos:
        video_id = video['video_id']
        if video_id not in stats:
            continue

        view_count = stats[video_id]['viewCount']
        if min_views <= view_count <= max_views:
            filtered.append({
                **video,
                'views': view_count
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

# ============================================================================
# DATA AGGREGATION
# ============================================================================

def aggregate_channels(videos: List[Dict], channel_stats: Dict[str, Dict], keyword: str) -> Dict[str, Dict]:
    """
    Aggregate videos by channel and add channel metadata.

    Args:
        videos: List of filtered videos with views
        channel_stats: Dict mapping channel_id to stats
        keyword: The keyword that found these videos

    Returns:
        Dict mapping channel_id to channel data with videos list
    """
    channels = {}

    for video in videos:
        channel_id = video['channel_id']

        if channel_id not in channel_stats:
            continue

        if channel_id not in channels:
            # Create new channel entry
            stats = channel_stats[channel_id]
            channels[channel_id] = {
                'channel_name': video['channel_name'],
                'channel_id': channel_id,
                'channel_url': f"youtube.com/channel/{channel_id}",
                'subscriber_count': stats['subscriberCount'],
                'total_videos': stats['videoCount'],
                'videos': []
            }

        # Add video to channel's video list
        channels[channel_id]['videos'].append({
            'title': video['title'],
            'url': f"youtube.com/watch?v={video['video_id']}",
            'views': video['views'],
            'keywords': [keyword] if keyword not in [k for v in channels[channel_id]['videos'] for k in v.get('keywords', [])] else []
        })

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
    """Calculate average views for a channel's videos."""
    videos = channel_data.get('videos', [])
    if not videos:
        return 0.0
    return sum(v['views'] for v in videos) / len(videos)

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

# ============================================================================
# DISPLAY
# ============================================================================

def display_channel_row(channel_data: Dict):
    """Display a single channel row from JSONL data."""
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.write(f"**{channel_data['channel_name']}**")
            st.caption(f"📺 {channel_data['total_videos']} videos")

        with col2:
            st.write(f"👥 {channel_data['subscriber_count']:,} subscribers")
            st.write(f"📊 Avg views: {channel_data['average_views']:.0f}")

        with col3:
            st.write(f"🔗 [Visit Channel](https://youtube.com/channel/{channel_data['channel_id']})")

        st.divider()

        st.write("**Videos Found:**")
        for video in channel_data['videos']:
            st.write(f"• {video['title']}")
            st.caption(f"Views: {video['views']} | [Watch](https://{video['url']})")

# ============================================================================
# MAIN
# ============================================================================

def main():
    global youtube
    try:
        youtube = init_youtube_client()
    except ValueError as e:
        st.error(f"Error: {str(e)}")
        return

    """Main execution function with Streamlit UI."""
    st.set_page_config(page_title="YouTube Podcast Finder", layout="wide")
    st.title("🎙️ YouTube Podcast Finder")

    # Input
    keyword = st.text_input("Enter a keyword to search for podcasts:", placeholder="e.g., AI product development")

    # Filter Settings
    with st.expander("🎯 Filter Settings", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Video Filters")
            enable_views_filter = st.checkbox("Filter by View Count", value=True)
            views_range = st.slider(
                "View Count Range",
                min_value=0,
                max_value=10000,
                value=(MIN_VIEWS, MAX_VIEWS),
                step=50,
                disabled=not enable_views_filter
            )

        with col2:
            st.subheader("Channel Filters")
            enable_videos_filter = st.checkbox("Filter by Video Count", value=True)
            videos_range = st.slider(
                "Channel Video Count",
                min_value=1,
                max_value=500,
                value=(MIN_CHANNEL_VIDEOS, MAX_CHANNEL_VIDEOS),
                step=1,
                disabled=not enable_videos_filter
            )

            enable_subscribers_filter = st.checkbox("Filter by Subscriber Count", value=True)
            subscribers_range = st.slider(
                "Subscriber Count Range",
                min_value=0,
                max_value=100000,
                value=(MIN_SUBSCRIBERS, MAX_SUBSCRIBERS),
                step=100,
                disabled=not enable_subscribers_filter
            )

    if not keyword:
        st.info("Enter a keyword above to start searching for podcasts.")
        return

    if st.button("Search Podcasts", type="primary"):
        # Extract filter values from UI
        min_views, max_views = views_range
        min_videos, max_videos = videos_range
        min_subs, max_subs = subscribers_range

        all_channels = {}

        # Process all steps in a single status block
        with st.status("🔍 Processing...", expanded=True) as status:
            # Step 1: Search for videos
            st.write("🔍 Searching for videos...")
            videos = search_videos(keyword)
            if not videos:
                st.error(f"No videos found for '{keyword}'")
                status.update(label="❌ No videos found", state="error")
                return
            st.write(f"✅ Found {len(videos)} videos")
            status.update(label=f"🔍 Found {len(videos)} videos")

            # Step 2: Get video statistics
            st.write("📊 Fetching video statistics...")
            video_ids = [v['video_id'] for v in videos]
            video_stats = get_video_statistics(video_ids)
            st.write("✅ Video statistics fetched")
            status.update(label=f"📊 Processing {len(videos)} videos")

            # Step 3: Filter by view count
            if enable_views_filter:
                st.write(f"🎯 Filtering videos by view count ({min_views:,}-{max_views:,})...")
                filtered_videos = filter_videos_by_views(videos, video_stats, min_views, max_views)
                if not filtered_videos:
                    st.error(f"No videos found with {min_views:,}-{max_views:,} views")
                    status.update(label="❌ No videos match criteria", state="error")
                    return
                st.write(f"✅ {len(filtered_videos)} videos match criteria")
                status.update(label=f"🎯 Filtered to {len(filtered_videos)} videos")
            else:
                st.write("⏭️ Skipping view count filter")
                # Add view counts to all videos
                filtered_videos = []
                for video in videos:
                    video_id = video['video_id']
                    if video_id in video_stats:
                        filtered_videos.append({
                            **video,
                            'views': video_stats[video_id]['viewCount']
                        })
                status.update(label=f"⏭️ {len(filtered_videos)} videos (no view filter)")

            # Step 4: Get channel statistics
            st.write("📺 Fetching channel statistics...")
            channel_ids = list(set(v['channel_id'] for v in filtered_videos))
            channel_stats = get_channel_statistics(channel_ids)
            st.write("✅ Channel statistics fetched")
            status.update(label=f"📺 Processing {len(channel_ids)} channels")

            # Step 5: Filter by channel video count
            if enable_videos_filter:
                st.write(f"🔄 Filtering channels by video count ({min_videos}-{max_videos})...")
                valid_channel_ids = filter_channels_by_video_count(channel_ids, channel_stats, min_videos, max_videos)
                filtered_videos = [v for v in filtered_videos if v['channel_id'] in valid_channel_ids]
                st.write(f"✅ {len(valid_channel_ids)} channels qualify")
                status.update(label=f"🔄 {len(valid_channel_ids)} channels qualify")
            else:
                st.write("⏭️ Skipping video count filter")
                valid_channel_ids = channel_ids
                status.update(label=f"⏭️ {len(valid_channel_ids)} channels (no video count filter)")

            # Step 5.5: Filter by subscriber count
            if enable_subscribers_filter:
                st.write(f"👥 Filtering channels by subscriber count ({min_subs:,}-{max_subs:,})...")
                valid_channel_ids = filter_channels_by_subscribers(valid_channel_ids, channel_stats, min_subs, max_subs)
                filtered_videos = [v for v in filtered_videos if v['channel_id'] in valid_channel_ids]
                st.write(f"✅ {len(valid_channel_ids)} channels after subscriber filter")
                status.update(label=f"👥 {len(valid_channel_ids)} channels match all filters")
            else:
                st.write("⏭️ Skipping subscriber count filter")
                status.update(label=f"⏭️ {len(valid_channel_ids)} channels (no subscriber filter)")

            # Step 6: Aggregate by channel
            st.write("📋 Aggregating results...")
            keyword_channels = aggregate_channels(filtered_videos, channel_stats, keyword)
            all_channels = merge_channels(all_channels, keyword_channels)
            st.write("✅ Results aggregated")
            status.update(label=f"✅ Complete - {len(all_channels)} channels found", state="complete")

        # Display results
        st.divider()
        st.subheader(f"Results: {len(all_channels)} channels found")

        if all_channels:
            for channel_id, channel_data in all_channels.items():
                avg_views = calculate_average_views(channel_data)
                channel_data['average_views'] = avg_views
                display_channel_row(channel_data)
        else:
            st.info("No channels match your criteria.")

if __name__ == '__main__':
    main()
