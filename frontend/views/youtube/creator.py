"""
Creator Discovery - Creator Detail Page
Detailed view for individual creator analysis.
"""

from datetime import datetime
from typing import Dict, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import api
from shared.youtube import RESULTS_PAGE, adopt_from_url, open_insights


def format_date(value: Optional[str], pattern: str) -> str:
    return datetime.fromisoformat(value).strftime(pattern) if value else 'N/A'


def create_score_gauge(score: int) -> go.Figure:
    """Create a plotly gauge chart for channel score."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={'x': [0, 1], 'y': [0, 1]},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, 40], 'color': "#ffcccc"},
                {'range': [40, 60], 'color': "#fff3cd"},
                {'range': [60, 100], 'color': "#d4edda"}
            ],
            'threshold': {
                'line': {'color': "black", 'width': 2},
                'thickness': 0.75,
                'value': score
            }
        }
    ))
    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=30, b=10),
    )
    return fig


def render_channel_header(channel_data: Dict):
    """Render channel header with thumbnail, basic info, and score gauge."""
    header_cols = st.columns([1, 3, 2])

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
            info_parts.append(f"Joined: {format_date(creation_date, '%b %Y')}")

        if info_parts:
            st.caption(" | ".join(info_parts))

    with header_cols[2]:
        # Overall Score Gauge
        score = channel_data.get('channel_score', 0)
        st.plotly_chart(create_score_gauge(score), width='stretch', key="score_gauge")
        st.caption(f"Overall Score: {channel_data['score_label']}")


def render_channel_description(channel_data: Dict):
    """Render channel description in an expander."""
    description = channel_data.get('description', '')
    if description:
        with st.expander("Channel Description"):
            st.write(description[:500] + "..." if len(description) > 500 else description)


def render_channel_metrics(channel_data: Dict):
    """Render channel metrics in organized sections."""
    st.subheader("Statistics")

    # Section 1 - Channel Overview
    st.markdown("### Channel Overview")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Subscribers", f"{channel_data['subscriber_count']:,}")

    with col2:
        st.metric("Total Videos", channel_data['total_videos'])

    with col3:
        total_views = channel_data.get('total_channel_views', 0)
        st.metric("Total Views", f"{total_views:,}")

    st.divider()

    # Section 2 - Publishing Activity
    st.markdown("### Publishing Activity")
    col4, col5, col6 = st.columns(3)

    with col4:
        st.metric("Publish Frequency", channel_data['publish_interval_label'])

    with col5:
        days_ago = channel_data.get('days_since_last_published')
        if days_ago is not None:
            st.metric("Last Video", f"{days_ago}d ago")
        else:
            st.metric("Last Video", "N/A")

    with col6:
        st.metric("Avg Duration", channel_data['avg_duration_label'])

    st.divider()

    # Section 3 - Performance Metrics
    st.markdown("### Performance Metrics")

    # Row 1: Engagement metrics
    col7, col8, col9 = st.columns(3)
    median_views = channel_data.get('median_views', 0)
    median_likes = channel_data.get('median_likes', 0)
    median_comments = channel_data.get('median_comments', 0)

    with col7:
        st.metric("Median Views", f"{median_views:,}")

    with col8:
        st.metric("Median Likes", f"{median_likes:,}")

    with col9:
        st.metric("Median Comments", f"{median_comments:,}")

    # Row 2: Ratios
    col10, col11, col12 = st.columns(3)

    with col10:
        ratio = channel_data.get('views_to_subs_ratio', 0)
        st.metric("Views-to-Subs Ratio", f"{ratio:.1f}%", channel_data['views_to_subs_label'])

    with col11:
        st.metric("Likes-to-Views Ratio", f"{channel_data['likes_to_views_ratio']:.2f}%")

    with col12:
        st.metric("Comments-to-Views Ratio", f"{channel_data['comments_to_views_ratio']:.2f}%")


def render_latest_videos(channel_data: Dict):
    """Render latest videos table and upload pattern chart."""
    st.subheader("Latest Videos")

    uploads_playlist_id = channel_data.get('uploads_playlist_id', '')

    if not uploads_playlist_id:
        st.info("Uploads playlist not available.")
        return

    latest = api.get(f"/youtube/playlists/{uploads_playlist_id}/videos", max_results=50)
    latest_videos = latest['videos']

    if not latest_videos:
        st.info("Could not load latest videos.")
        return

    # Videos table
    latest_video_data = []
    for v in latest_videos:
        latest_video_data.append({
            'Title': v['title'],
            'Views': v['views'],
            'Published': format_date(v.get('published_at'), '%b %d, %Y'),
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

    if latest['upload_pattern']:
        chart_data = pd.DataFrame(latest['upload_pattern']).rename(
            columns={'month': 'Month', 'uploads': 'Uploads'}
        )
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
        video_data.append({
            'Title': v['title'],
            'Views': v['views'],
            'Published': format_date(v.get('published_at'), '%b %d, %Y'),
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
    search_id = adopt_from_url('search_id', 'search')
    channel_id = adopt_from_url('selected_channel', 'channel')
    if not (search_id and channel_id):
        st.warning("No creator selected. Please select a creator from results.")
        if st.button("Go to Results"):
            st.switch_page(RESULTS_PAGE)
        return

    try:
        channel_data = api.get(f"/youtube/searches/{search_id}/channels/{channel_id}")
    except api.ApiError as exc:
        st.error(str(exc))
        if st.button("Back to Results"):
            st.switch_page(RESULTS_PAGE)
        return

    # Back button
    back_col, insights_col = st.columns([4, 1])
    if back_col.button("← Back to Results"):
        st.session_state.selected_channel = None
        st.switch_page(RESULTS_PAGE)
    if insights_col.button("💬 Audience insights", width='stretch',
                           help="Turn this creator's comments into content ideas"):
        open_insights(channel_id)

    st.divider()

    # Render all sections
    render_channel_header(channel_data)
    render_channel_description(channel_data)

    st.divider()
    render_channel_metrics(channel_data)

    st.divider()
    render_latest_videos(channel_data)

    st.divider()
    render_search_videos(channel_data)


main()
