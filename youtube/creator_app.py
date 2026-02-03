#!/usr/bin/env python3
"""
Creator Discovery - Streamlit Application
Find creators for collaboration opportunities (promotions, appearances, sponsorships).

Installation:
    1. pip install -r requirements.txt
    2. Create a .env file in the same directory with: YOUTUBE_API_KEY=your_api_key_here
    3. Get your API key from: https://console.cloud.google.com/
    4. Run: streamlit run creator_app.py
"""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from creator_service import (
    YouTubeService,
    filter_videos_by_views,
    filter_channels_by_video_count,
    filter_channels_by_subscribers,
    filter_channels_by_activity,
    aggregate_channels,
    merge_channels,
    sort_channels,
    format_publish_interval,
    SortOption,
    MIN_VIEWS,
    MAX_VIEWS,
    MIN_CHANNEL_VIDEOS,
    MAX_CHANNEL_VIDEOS,
    MIN_SUBSCRIBERS,
    MAX_SUBSCRIBERS,
)

# ============================================================================
# FILTER PRESETS
# ============================================================================

VIEW_PRESETS = {
    "Any": (0, 10_000_000),
    "< 1K": (0, 1_000),
    "1K - 10K": (1_000, 10_000),
    "10K - 100K": (10_000, 100_000),
    "100K+": (100_000, 10_000_000),
}

SUBSCRIBER_PRESETS = {
    "Any": (0, 100_000_000),
    "< 1K": (0, 1_000),
    "1K - 10K": (1_000, 10_000),
    "10K - 100K": (10_000, 100_000),
    "100K - 1M": (100_000, 1_000_000),
    "1M+": (1_000_000, 100_000_000),
}

ACTIVITY_PRESETS = {
    "Any": None,
    "Active (30 days)": 30,
    "Active (90 days)": 90,
    "Active (1 year)": 365,
}

SORT_OPTIONS = {
    "Relevance": SortOption.RELEVANCE,
    "Median Views": SortOption.MEDIAN_VIEWS,
    "Subscribers": SortOption.SUBSCRIBERS,
    "Most Recent": SortOption.ACTIVITY,
}

# ============================================================================
# CACHED WRAPPER FUNCTIONS
# ============================================================================

@st.cache_data(show_spinner=False)
def cached_search_videos(_service: YouTubeService, keyword: str, max_results: int = 50) -> List[Dict]:
    """Cached wrapper for YouTube video search."""
    return _service.search_videos(keyword, max_results)


@st.cache_data(show_spinner=False)
def cached_get_video_statistics(_service: YouTubeService, video_ids: List[str]) -> Dict[str, Dict]:
    """Cached wrapper for video statistics."""
    return _service.get_video_statistics(video_ids)


@st.cache_data(show_spinner=False)
def cached_get_channel_statistics(_service: YouTubeService, channel_ids: List[str]) -> Dict[str, Dict]:
    """Cached wrapper for channel statistics."""
    return _service.get_channel_statistics(channel_ids)


@st.cache_data(show_spinner=False)
def cached_get_channel_latest_videos(_service: YouTubeService, uploads_playlist_id: str, max_results: int = 10) -> List[Dict]:
    """Cached wrapper for fetching channel's latest videos."""
    return _service.get_channel_latest_videos(uploads_playlist_id, max_results)

# ============================================================================
# SERVICE INITIALIZATION
# ============================================================================

def init_app() -> Optional[YouTubeService]:
    """Initialize YouTube service with error handling."""
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
# UI COMPONENTS - FILTERS
# ============================================================================

def render_filters() -> Dict:
    """Render horizontal filter dropdowns."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        view_preset = st.selectbox(
            "Views",
            options=list(VIEW_PRESETS.keys()),
            index=0,
            help="Filter by median view count"
        )

    with col2:
        sub_preset = st.selectbox(
            "Subscribers",
            options=list(SUBSCRIBER_PRESETS.keys()),
            index=2,
            help="Filter by subscriber count"
        )

    with col3:
        activity_preset = st.selectbox(
            "Activity",
            options=list(ACTIVITY_PRESETS.keys()),
            index=1,
            help="Filter by recent activity"
        )

    with col4:
        sort_by = st.selectbox(
            "Sort by",
            options=list(SORT_OPTIONS.keys()),
            index=0,
            help="Sort results"
        )

    return {
        'view_range': VIEW_PRESETS[view_preset],
        'subscriber_range': SUBSCRIBER_PRESETS[sub_preset],
        'activity_days': ACTIVITY_PRESETS[activity_preset],
        'sort_by': SORT_OPTIONS[sort_by],
    }

# ============================================================================
# UI COMPONENTS - OVERVIEW TABLE
# ============================================================================

def render_overview_table(channels: List[Dict]) -> Optional[str]:
    """
    Render results in a clean table format.

    Returns:
        Selected channel_id if a row is clicked, None otherwise
    """
    if not channels:
        st.info("No creators match your criteria.")
        return None

    # Prepare data for table
    table_data = []
    for c in channels:
        last_pub = c.get('last_published')
        if last_pub:
            days_ago = (datetime.now(timezone.utc) - last_pub).days
            last_pub_str = f"{days_ago}d ago" if days_ago < 30 else last_pub.strftime('%b %d, %Y')
        else:
            last_pub_str = "N/A"

        table_data.append({
            'Channel': c['channel_name'],
            'Subscribers': c['subscriber_count'],
            'Median Views': c.get('median_views', 0),
            'Publish Interval': format_publish_interval(c.get('publish_interval_days')),
            'Last Published': last_pub_str,
            'Videos Found': len(c.get('videos', [])),
            'channel_id': c['channel_id'],
        })

    df = pd.DataFrame(table_data)

    # Display count
    st.caption(f"{len(channels)} creators found")

    # Use data_editor for selection
    selected = st.dataframe(
        df,
        column_config={
            'Channel': st.column_config.TextColumn('Channel', width='medium'),
            'Subscribers': st.column_config.NumberColumn('Subs', format='%d'),
            'Median Views': st.column_config.NumberColumn('Median Views', format='%d'),
            'Publish Interval': st.column_config.TextColumn('Frequency', width='small'),
            'Last Published': st.column_config.TextColumn('Last Active', width='small'),
            'Videos Found': st.column_config.NumberColumn('Found', width='small'),
            'channel_id': None,
        },
        hide_index=True,
        width='stretch',
        on_select="rerun",
        selection_mode="single-row",
    )

    # Check if a row was selected
    selection = selected.get("selection") if selected else None
    rows = selection.get("rows") if selection else None
    if rows:
        selected_idx = rows[0]
        return table_data[selected_idx]['channel_id']

    return None

# ============================================================================
# UI COMPONENTS - DETAIL PAGE
# ============================================================================

def render_channel_detail(channel_data: Dict, service: YouTubeService):
    """Render detailed view for selected channel."""

    # Back button
    if st.button("← Back to Results"):
        st.session_state.selected_channel = None
        st.rerun()

    st.divider()

    # Channel header with thumbnail
    header_cols = st.columns([1, 4])

    with header_cols[0]:
        thumbnail_url = channel_data.get('thumbnail_url', '')
        if thumbnail_url:
            st.image(thumbnail_url, width=120)

    with header_cols[1]:
        st.subheader(channel_data['channel_name'])
        st.markdown(f"[Visit Channel](https://youtube.com/channel/{channel_data['channel_id']})")

        # Country and creation date info
        country = channel_data.get('country', '')
        creation_date = channel_data.get('created_at')

        info_parts = []
        if country:
            info_parts.append(f"Country: {country}")
        if creation_date:
            if isinstance(creation_date, datetime):
                info_parts.append(f"Created: {creation_date.strftime('%b %d, %Y')}")
            else:
                info_parts.append(f"Created: {creation_date}")

        if info_parts:
            st.caption(" | ".join(info_parts))

    # Metrics row 1
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Subscribers", f"{channel_data['subscriber_count']:,}")

    with col2:
        st.metric("Median Views", f"{channel_data.get('median_views', 0):,}")

    with col3:
        interval = format_publish_interval(channel_data.get('publish_interval_days'))
        st.metric("Publish Frequency", interval)

    with col4:
        last_pub = channel_data.get('last_published')
        if last_pub:
            days_ago = (datetime.now(timezone.utc) - last_pub).days
            st.metric("Last Published", f"{days_ago} days ago")
        else:
            st.metric("Last Published", "N/A")

    # Metrics row 2
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        st.metric("Total Videos", channel_data['total_videos'])

    with col6:
        st.metric("Average Views", f"{channel_data.get('average_views', 0):,.0f}")

    with col7:
        total_views = channel_data.get('total_channel_views', 0)
        st.metric("Total Channel Views", f"{total_views:,}")

    with col8:
        country_display = channel_data.get('country', 'N/A')
        st.metric("Country", country_display if country_display else "N/A")

    st.divider()

    # Latest Videos section (NEW)
    st.subheader("Latest Videos")

    uploads_playlist_id = channel_data.get('uploads_playlist_id', '')

    if uploads_playlist_id:
        latest_videos = cached_get_channel_latest_videos(service, uploads_playlist_id, max_results=50)

        if latest_videos:
            latest_video_data = []
            for v in latest_videos:
                pub_date = v.get('published_at')
                pub_str = pub_date.strftime('%b %d, %Y') if pub_date else 'N/A'
                latest_video_data.append({
                    'Title': v['title'],
                    'Views': v['views'],
                    'Published': pub_str,
                    'URL': f"https://{v['url']}",
                })

            latest_df = pd.DataFrame(latest_video_data)
            st.dataframe(
                latest_df,
                column_config={
                    'Title': st.column_config.TextColumn('Title', width='large'),
                    'Views': st.column_config.NumberColumn('Views', format='%d'),
                    'Published': st.column_config.TextColumn('Published'),
                    'URL': st.column_config.LinkColumn('Link', display_text='Watch'),
                },
                hide_index=True,
                width='stretch',
            )
        else:
            st.info("Could not load latest videos.")
    else:
        st.info("Uploads playlist not available.")

    st.divider()

    # Videos found section (from search)
    st.subheader("Videos Found (from search)")
    videos = channel_data.get('videos', [])

    if videos:
        video_data = []
        for v in videos:
            pub_date = v.get('published_at')
            pub_str = pub_date.strftime('%b %d, %Y') if pub_date else 'N/A'
            video_data.append({
                'Title': v['title'],
                'Views': v['views'],
                'Published': pub_str,
                'URL': f"https://{v['url']}",
            })

        video_df = pd.DataFrame(video_data)
        st.dataframe(
            video_df,
            column_config={
                'Title': st.column_config.TextColumn('Title', width='large'),
                'Views': st.column_config.NumberColumn('Views', format='%d'),
                'Published': st.column_config.TextColumn('Published'),
                'URL': st.column_config.LinkColumn('Link', display_text='Watch'),
            },
            hide_index=True,
            width='stretch',
        )
    else:
        st.info("No videos found for this channel in search.")

# ============================================================================
# SEARCH PROCESSING
# ============================================================================

def process_search(service: YouTubeService, keyword: str, filters: Dict) -> Dict[str, Dict]:
    """Process search with given filters and return results."""
    min_views, max_views = filters['view_range']
    min_subs, max_subs = filters['subscriber_range']

    all_channels = {}

    with st.status("Searching...", expanded=True) as status:
        # Step 1: Search for videos
        st.write("Searching for videos...")
        videos = cached_search_videos(service, keyword)
        if not videos:
            st.error(f"No videos found for '{keyword}'")
            status.update(label="No videos found", state="error")
            return {}
        st.write(f"Found {len(videos)} videos")

        # Step 2: Get video statistics
        st.write("Fetching video statistics...")
        video_ids = [v['video_id'] for v in videos]
        video_stats = cached_get_video_statistics(service, video_ids)

        # Step 3: Filter by view count
        st.write("Filtering by view count...")
        filtered_videos = filter_videos_by_views(videos, video_stats, min_views, max_views)
        if not filtered_videos:
            st.error(f"No videos found with {min_views:,}-{max_views:,} views")
            status.update(label="No matching videos", state="error")
            return {}
        st.write(f"{len(filtered_videos)} videos match view criteria")

        # Step 4: Get channel statistics
        st.write("Fetching channel statistics...")
        channel_ids = list(set(v['channel_id'] for v in filtered_videos))
        channel_stats = cached_get_channel_statistics(service, channel_ids)

        # Step 5: Filter by subscriber count
        st.write("Filtering by subscribers...")
        valid_channel_ids = filter_channels_by_subscribers(channel_ids, channel_stats, min_subs, max_subs)
        filtered_videos = [v for v in filtered_videos if v['channel_id'] in valid_channel_ids]

        if not filtered_videos:
            st.error("No channels match subscriber criteria")
            status.update(label="No matching channels", state="error")
            return {}

        # Step 6: Aggregate by channel
        st.write("Aggregating results...")
        keyword_channels = aggregate_channels(filtered_videos, channel_stats, keyword)
        all_channels = merge_channels(all_channels, keyword_channels)

        # Step 7: Filter by activity if specified
        activity_days = filters.get('activity_days')
        if activity_days:
            st.write(f"Filtering by activity (last {activity_days} days)...")
            all_channels = filter_channels_by_activity(all_channels, activity_days)

        st.write(f"Found {len(all_channels)} creators")
        status.update(label=f"Found {len(all_channels)} creators", state="complete")

    return all_channels

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point."""
    load_dotenv()

    service = init_app()
    if service is None:
        return

    st.set_page_config(page_title="Creator Discovery", page_icon="🔍", layout="wide")
    st.title("Creator Discovery")
    st.caption("Find creators for collaboration opportunities")

    # Initialize session state
    if 'search_results' not in st.session_state:
        st.session_state.search_results = {}
    if 'selected_channel' not in st.session_state:
        st.session_state.selected_channel = None

    # Check if viewing detail page
    if st.session_state.selected_channel:
        channel_id = st.session_state.selected_channel
        if channel_id in st.session_state.search_results:
            render_channel_detail(st.session_state.search_results[channel_id], service)
            return

    # Overview page
    keyword = st.text_input(
        "Search for creators:",
        placeholder="e.g., tech reviews, cooking tutorials, fitness tips"
    )

    filters = render_filters()

    if not keyword:
        st.info("Enter a search term above to discover creators.")
        return

    if st.button("Search", type="primary"):
        channels = process_search(service, keyword, filters)
        st.session_state.search_results = channels

    # Display results
    if st.session_state.search_results:
        st.divider()

        # Sort channels
        sorted_channels = sort_channels(
            st.session_state.search_results,
            filters['sort_by']
        )

        # Render table and handle selection
        selected_id = render_overview_table(sorted_channels)

        if selected_id:
            st.session_state.selected_channel = selected_id
            st.rerun()


if __name__ == '__main__':
    main()
