#!/usr/bin/env python3
"""
YouTube Podcast Finder - Streamlit Application
Finds small podcasts (100-1,000 views) suitable for guest appearances.

Installation:
    1. pip install -r requirements.txt
    2. Create a .env file in the same directory with: YOUTUBE_API_KEY=your_api_key_here
    3. Get your API key from: https://console.cloud.google.com/
    4. Run: streamlit run podcast_app.py

Output:
    Results are saved to podcasts.jsonl with one channel per line.
"""

import os
from typing import Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

# Import from service layer
from podcast_service import (
    # Service class
    YouTubeService,
    # Filter functions
    filter_videos_by_views,
    filter_channels_by_video_count,
    filter_channels_by_subscribers,
    # Aggregation functions
    aggregate_channels,
    merge_channels,
    # Output functions
    calculate_average_views,
    write_channels_to_jsonl,
    # Configuration constants (for UI defaults)
    MIN_VIEWS,
    MAX_VIEWS,
    MIN_CHANNEL_VIDEOS,
    MAX_CHANNEL_VIDEOS,
    MIN_SUBSCRIBERS,
    MAX_SUBSCRIBERS,
    MAX_RESULTS_PER_KEYWORD,
)

# ============================================================================
# CACHED WRAPPER FUNCTIONS
# ============================================================================

@st.cache_data(show_spinner=False)
def cached_search_videos(_service: YouTubeService, keyword: str, max_results: int = 50) -> List[Dict]:
    """
    Cached wrapper for YouTube video search.

    Args:
        _service: YouTubeService instance (underscore prefix tells Streamlit not to hash)
        keyword: Search keyword
        max_results: Max results per API call

    Returns:
        List of video dictionaries
    """
    return _service.search_videos(keyword, max_results)

@st.cache_data(show_spinner=False)
def cached_get_video_statistics(_service: YouTubeService, video_ids: List[str]) -> Dict[str, Dict]:
    """
    Cached wrapper for video statistics.

    Args:
        _service: YouTubeService instance
        video_ids: List of video IDs

    Returns:
        Dict mapping video_id to statistics
    """
    return _service.get_video_statistics(video_ids)

@st.cache_data(show_spinner=False)
def cached_get_channel_statistics(_service: YouTubeService, channel_ids: List[str]) -> Dict[str, Dict]:
    """
    Cached wrapper for channel statistics.

    Args:
        _service: YouTubeService instance
        channel_ids: List of channel IDs

    Returns:
        Dict mapping channel_id to statistics
    """
    return _service.get_channel_statistics(channel_ids)

# ============================================================================
# SERVICE INITIALIZATION
# ============================================================================

def init_app() -> Optional[YouTubeService]:
    """
    Initialize YouTube service with error handling.

    Returns:
        YouTubeService instance or None if initialization fails
    """
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        st.error("YOUTUBE_API_KEY not found in environment. Please add it to .env file.")
        st.info("Get your API key from: https://console.cloud.google.com/")
        return None

    try:
        return YouTubeService(api_key)
    except Exception as e:
        st.error(f"Error initializing YouTube service: {str(e)}")
        return None

# ============================================================================
# UI COMPONENTS
# ============================================================================

def display_channel_row(channel_data: Dict):
    """
    Display a single channel row from channel data.

    Args:
        channel_data: Channel dictionary with metadata and videos
    """
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

def render_filter_settings() -> Dict:
    """
    Render filter settings UI and return configuration.

    Returns:
        Dict with filter configuration
    """
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

    return {
        'enable_views_filter': enable_views_filter,
        'views_range': views_range,
        'enable_videos_filter': enable_videos_filter,
        'videos_range': videos_range,
        'enable_subscribers_filter': enable_subscribers_filter,
        'subscribers_range': subscribers_range,
    }

def process_search(service: YouTubeService, keyword: str, filters: Dict) -> Dict[str, Dict]:
    """
    Process search with given filters and return results.

    Args:
        service: YouTubeService instance
        keyword: Search keyword
        filters: Filter configuration dict

    Returns:
        Dict mapping channel_id to channel data
    """
    # Extract filter values
    enable_views_filter = filters['enable_views_filter']
    min_views, max_views = filters['views_range']
    enable_videos_filter = filters['enable_videos_filter']
    min_videos, max_videos = filters['videos_range']
    enable_subscribers_filter = filters['enable_subscribers_filter']
    min_subs, max_subs = filters['subscribers_range']

    all_channels = {}

    # Process all steps in a single status block
    with st.status("🔍 Processing...", expanded=True) as status:
        # Step 1: Search for videos
        st.write("🔍 Searching for videos...")
        videos = cached_search_videos(service, keyword)
        if not videos:
            st.error(f"No videos found for '{keyword}'")
            status.update(label="❌ No videos found", state="error")
            return {}
        st.write(f"✅ Found {len(videos)} videos")
        status.update(label=f"🔍 Found {len(videos)} videos")

        # Step 2: Get video statistics
        st.write("📊 Fetching video statistics...")
        video_ids = [v['video_id'] for v in videos]
        video_stats = cached_get_video_statistics(service, video_ids)
        st.write("✅ Video statistics fetched")
        status.update(label=f"📊 Processing {len(videos)} videos")

        # Step 3: Filter by view count
        if enable_views_filter:
            st.write(f"🎯 Filtering videos by view count ({min_views:,}-{max_views:,})...")
            filtered_videos = filter_videos_by_views(videos, video_stats, min_views, max_views)
            if not filtered_videos:
                st.error(f"No videos found with {min_views:,}-{max_views:,} views")
                status.update(label="❌ No videos match criteria", state="error")
                return {}
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
        channel_stats = cached_get_channel_statistics(service, channel_ids)
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

        # Step 6: Filter by subscriber count
        if enable_subscribers_filter:
            st.write(f"👥 Filtering channels by subscriber count ({min_subs:,}-{max_subs:,})...")
            valid_channel_ids = filter_channels_by_subscribers(valid_channel_ids, channel_stats, min_subs, max_subs)
            filtered_videos = [v for v in filtered_videos if v['channel_id'] in valid_channel_ids]
            st.write(f"✅ {len(valid_channel_ids)} channels after subscriber filter")
            status.update(label=f"👥 {len(valid_channel_ids)} channels match all filters")
        else:
            st.write("⏭️ Skipping subscriber count filter")
            status.update(label=f"⏭️ {len(valid_channel_ids)} channels (no subscriber filter)")

        # Step 7: Aggregate by channel
        st.write("📋 Aggregating results...")
        keyword_channels = aggregate_channels(filtered_videos, channel_stats, keyword)
        all_channels = merge_channels(all_channels, keyword_channels)
        st.write("✅ Results aggregated")
        status.update(label=f"✅ Complete - {len(all_channels)} channels found", state="complete")

    return all_channels

def render_search_results(channels: Dict[str, Dict]):
    """
    Render search results in UI.

    Args:
        channels: Dict mapping channel_id to channel data
    """
    st.divider()
    st.subheader(f"Results: {len(channels)} channels found")

    if channels:
        for channel_id, channel_data in channels.items():
            # Ensure average_views is calculated
            avg_views = calculate_average_views(channel_data)
            channel_data['average_views'] = avg_views
            display_channel_row(channel_data)
    else:
        st.info("No channels match your criteria.")

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point."""
    # 1. Load environment variables
    load_dotenv()

    # 2. Initialize service
    service = init_app()
    if service is None:
        return

    # 3. Set up Streamlit page
    st.set_page_config(page_title="YouTube Podcast Finder", layout="wide")
    st.title("🎙️ YouTube Podcast Finder")

    # 4. Render input
    keyword = st.text_input(
        "Enter a keyword to search for podcasts:",
        placeholder="e.g., AI product development"
    )

    # 5. Render filter settings
    filters = render_filter_settings()

    # 6. Handle search
    if not keyword:
        st.info("Enter a keyword above to start searching for podcasts.")
        return

    if st.button("Search Podcasts", type="primary"):
        channels = process_search(service, keyword, filters)
        render_search_results(channels)

if __name__ == '__main__':
    main()
