"""
Creator Discovery - Results Page
Display and filter search results.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from backend.youtube.filters import filter_channels
from backend.youtube.metrics import format_publish_interval
from backend.youtube.sorting import sort_channels
from frontend.state import init_session_state
from frontend.youtube_components import (
    CREATOR_PAGE,
    SEARCH_PAGE,
    render_filters,
    require_search_results,
)


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

    # Use dataframe for selection
    selected = st.dataframe(
        df,
        column_config={
            'Channel': st.column_config.TextColumn('Channel', width='medium'),
            'Subscribers': st.column_config.NumberColumn('Subs', format='%d'),
            'Median Views': st.column_config.NumberColumn('Median Views', format='%d'),
            'Publish Interval': st.column_config.TextColumn('Frequency', width='small'),
            'Last Published': st.column_config.TextColumn('Last Active', width='small'),
            'Videos Found': st.column_config.NumberColumn('Found', width='small'),
            'channel_id': None,  # Hidden column
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


def main():
    """Results page - Display filtered search results."""
    init_session_state()

    if not require_search_results():
        return

    st.title("Search Results")

    # Show what was searched
    keyword = st.session_state.get('search_keyword', '')
    if keyword:
        st.caption(f"Results for: \"{keyword}\"")

    # Filters
    st.subheader("Filters")
    filters = render_filters()

    st.divider()

    # Filter and sort results
    filtered_channels = filter_channels(
        st.session_state.search_results,
        filters['view_range'],
        filters['subscriber_range'],
        filters['activity_days'],
    )
    sorted_channels = sort_channels(filtered_channels, filters['sort_by'])

    selected_id = render_overview_table(sorted_channels)

    if selected_id:
        st.session_state.selected_channel = selected_id
        st.switch_page(CREATOR_PAGE)

    # Link back to search
    st.divider()
    if st.button("New Search"):
        st.switch_page(SEARCH_PAGE)


main()
