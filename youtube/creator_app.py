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
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from config import VIEW_PRESETS, SUBSCRIBER_PRESETS, ACTIVITY_PRESETS
from youtube_api import YouTubeService
from sorting import SortOption, SORT_OPTIONS, sort_channels
from metrics import format_publish_interval, format_duration, get_views_to_subs_label, get_score_label
from pipeline import search_creators, SearchError

# ============================================================================
# CACHED WRAPPER FUNCTIONS
# ============================================================================

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

        # Channel Score badge
        score = channel_data.get('channel_score', 0)
        score_label = get_score_label(score)
        score_color = "green" if score >= 60 else "orange" if score >= 40 else "red"
        st.markdown(f"**Overall Score:** :{score_color}[{score}/100 - {score_label}]")

        # Country and creation date info
        country = channel_data.get('country', '')
        creation_date = channel_data.get('created_at')

        info_parts = []
        if country:
            info_parts.append(f"Country: {country}")
        if creation_date:
            if isinstance(creation_date, datetime):
                info_parts.append(f"Joined: {creation_date.strftime('%b %Y')}")
            else:
                info_parts.append(f"Joined: {creation_date}")

        if info_parts:
            st.caption(" | ".join(info_parts))

    # Channel description
    description = channel_data.get('description', '')
    if description:
        with st.expander("Channel Description"):
            st.write(description[:500] + "..." if len(description) > 500 else description)

    # Metrics row 1 - Channel Overview
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Subscribers", f"{channel_data['subscriber_count']:,}")

    with col2:
        st.metric("Total Videos", channel_data['total_videos'])

    with col3:
        total_views = channel_data.get('total_channel_views', 0)
        st.metric("Total Views", f"{total_views:,}")

    with col4:
        created = channel_data.get('created_at')
        if created and isinstance(created, datetime):
            st.metric("Joined", created.strftime('%b %Y'))
        else:
            st.metric("Joined", "N/A")

    # Metrics row 2 - Activity
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        interval = format_publish_interval(channel_data.get('publish_interval_days'))
        st.metric("Publish Frequency", interval)

    with col6:
        last_pub = channel_data.get('last_published')
        if last_pub:
            days_ago = (datetime.now(timezone.utc) - last_pub).days
            st.metric("Last Video", f"{days_ago}d ago")
        else:
            st.metric("Last Video", "N/A")

    with col7:
        avg_dur = channel_data.get('avg_duration', 0)
        st.metric("Avg Duration", format_duration(avg_dur))

    with col8:
        st.metric("Median Views", f"{channel_data.get('median_views', 0):,}")

    # Metrics row 3 - Performance
    st.subheader("Performance Metrics")
    col9, col10, col11, col12 = st.columns(4)

    with col9:
        ratio = channel_data.get('views_to_subs_ratio', 0)
        label = get_views_to_subs_label(ratio)
        st.metric("Views-to-Subs Ratio", f"{ratio:.1f}%", label)

    with col10:
        st.metric("Median Likes", f"{channel_data.get('median_likes', 0):,}")

    with col11:
        st.metric("Median Comments", f"{channel_data.get('median_comments', 0):,}")

    with col12:
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

            # Upload Pattern Chart
            st.subheader("Upload Pattern (6 months)")

            # Group by month
            month_counts = Counter()
            for v in latest_videos:
                pub_date = v.get('published_at')
                if pub_date:
                    month_key = pub_date.strftime('%b')
                    month_counts[month_key] += 1

            if month_counts:
                months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

                # Get last 6 months in order
                current_month = datetime.now().month
                last_6_months = []
                for i in range(5, -1, -1):
                    month_idx = (current_month - i - 1) % 12
                    last_6_months.append(months_order[month_idx])

                chart_data = pd.DataFrame({
                    'Month': last_6_months,
                    'Uploads': [month_counts.get(m, 0) for m in last_6_months]
                })

                st.bar_chart(chart_data.set_index('Month'))
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
    """Process search with UI progress updates."""
    with st.status("Searching...", expanded=True) as status:
        def on_progress(msg: str):
            st.write(msg)

        try:
            channels = search_creators(
                service=service,
                keyword=keyword,
                view_range=filters['view_range'],
                subscriber_range=filters['subscriber_range'],
                activity_days=filters.get('activity_days'),
                on_progress=on_progress,
            )

            if channels:
                status.update(label=f"Found {len(channels)} creators", state="complete")
            else:
                status.update(label="No creators found", state="error")

            return channels

        except SearchError as e:
            st.error(str(e))
            status.update(label="Search failed", state="error")
            return {}

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
