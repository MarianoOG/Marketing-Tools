"""
Creator Discovery - Results Page
Display and filter search results.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from filters import filter_channels
from metrics import format_publish_interval
from sorting import sort_channels
from shared.state import init_session_state, require_search_results
from shared.components import render_filters


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
    st.set_page_config(page_title="Results - Creator Discovery", page_icon="📊", layout="wide")

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
        st.switch_page("pages/2_Creator.py")

    # Link back to search
    st.divider()
    if st.button("New Search"):
        st.switch_page("Home.py")


if __name__ == '__main__':
    main()
