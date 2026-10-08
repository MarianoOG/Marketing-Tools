"""
Creator Discovery - Results Page
Display and filter a saved search. Filtering and sorting happen in the backend
on the saved result, so changing a filter spends no API quota.
"""

from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

import api
from shared.youtube import CREATOR_PAGE, SEARCH_PAGE, adopt_from_url, open_insights, render_filters


def last_published_text(channel: Dict) -> str:
    days_ago = channel.get('days_since_last_published')
    if days_ago is None:
        return "N/A"
    if days_ago < 30:
        return f"{days_ago}d ago"
    return datetime.fromisoformat(channel['last_published']).strftime('%b %d, %Y')


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
        table_data.append({
            'Channel': c['channel_name'],
            'Subscribers': c['subscriber_count'],
            'Median Views': c.get('median_views', 0),
            'Publish Interval': c['publish_interval_label'],
            'Last Published': last_published_text(c),
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
    search_id = adopt_from_url('search_id', 'search')
    if not search_id:
        st.warning("No search results available. Please perform a search first.")
        if st.button("Go to Search"):
            st.switch_page(SEARCH_PAGE)
        return

    st.title("Search Results")

    # Filters
    st.subheader("Filters")
    filters = render_filters()

    try:
        results = api.get(f"/youtube/searches/{search_id}/channels", **filters)
    except api.ApiError as exc:
        st.error(str(exc))
        if st.button("Go to Search"):
            st.session_state.search_id = None
            st.switch_page(SEARCH_PAGE)
        return

    # Show what was searched
    caption_col, insights_col = st.columns([4, 1])
    caption_col.caption(f"Results for: \"{results['keyword']}\"")
    if insights_col.button("💬 Audience insights", width='stretch',
                           help="Turn the comments of this niche's most-discussed videos into content ideas"):
        open_insights()

    st.divider()

    selected_id = render_overview_table(results['channels'])

    if selected_id:
        st.session_state.selected_channel = selected_id
        st.switch_page(CREATOR_PAGE)

    # Link back to search
    st.divider()
    if st.button("New Search"):
        st.switch_page(SEARCH_PAGE)


main()
