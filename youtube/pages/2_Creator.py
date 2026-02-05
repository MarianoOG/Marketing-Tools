"""
Creator Discovery - Creator Detail Page
Detailed view for individual creator analysis.
"""

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd
import streamlit as st

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from metrics import (
    format_publish_interval,
    format_duration,
    get_views_to_subs_label,
    get_score_label,
)
from shared.state import init_session_state, get_service, require_selected_channel
from shared.components import cached_get_channel_latest_videos


def render_channel_header(channel_data: Dict):
    """Render channel header with thumbnail and basic info."""
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


def render_channel_description(channel_data: Dict):
    """Render channel description in an expander."""
    description = channel_data.get('description', '')
    if description:
        with st.expander("Channel Description"):
            st.write(description[:500] + "..." if len(description) > 500 else description)


def render_channel_metrics(channel_data: Dict):
    """Render channel metrics in organized rows."""
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


def render_latest_videos(channel_data: Dict, service):
    """Render latest videos table and upload pattern chart."""
    st.subheader("Latest Videos")

    uploads_playlist_id = channel_data.get('uploads_playlist_id', '')

    if not uploads_playlist_id:
        st.info("Uploads playlist not available.")
        return

    latest_videos = cached_get_channel_latest_videos(service, uploads_playlist_id, max_results=50)

    if not latest_videos:
        st.info("Could not load latest videos.")
        return

    # Videos table
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


def render_search_videos(channel_data: Dict):
    """Render videos found from search."""
    st.subheader("Videos Found (from search)")
    videos = channel_data.get('videos', [])

    if not videos:
        st.info("No videos found for this channel in search.")
        return

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


def main():
    """Creator detail page."""
    st.set_page_config(page_title="Creator - Creator Discovery", page_icon="👤", layout="wide")

    init_session_state()

    if not require_selected_channel():
        return

    service = get_service()
    if service is None:
        st.error("Service not initialized.")
        return

    channel_id = st.session_state.selected_channel
    channel_data = st.session_state.search_results.get(channel_id)

    if not channel_data:
        st.error("Channel data not found.")
        if st.button("Back to Results"):
            st.switch_page("pages/1_Results.py")
        return

    # Back button
    if st.button("← Back to Results"):
        st.switch_page("pages/1_Results.py")

    st.divider()

    # Render all sections
    render_channel_header(channel_data)
    render_channel_description(channel_data)
    render_channel_metrics(channel_data)

    st.divider()
    render_latest_videos(channel_data, service)

    st.divider()
    render_search_videos(channel_data)


if __name__ == '__main__':
    main()
