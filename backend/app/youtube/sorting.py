"""
Sorting Logic

Sort options and functions for ordering channel results.
"""

from datetime import datetime
from typing import Dict, List


class SortOption:
    """Sort options for channel results."""
    RELEVANCE = "relevance"
    MEDIAN_VIEWS = "median_views"
    SUBSCRIBERS = "subscribers"
    ACTIVITY = "activity"


SORT_OPTIONS = {
    "Relevance": SortOption.RELEVANCE,
    "Median Views": SortOption.MEDIAN_VIEWS,
    "Subscribers": SortOption.SUBSCRIBERS,
    "Most Recent": SortOption.ACTIVITY,
}


def sort_channels(channels: Dict[str, Dict], sort_by: str, descending: bool = True) -> List[Dict]:
    """
    Sort channels by specified criteria.

    Args:
        channels: Dict mapping channel_id to channel data
        sort_by: One of SortOption values
        descending: Sort in descending order (default True)

    Returns:
        List of channel data dicts (not dict) to preserve sort order
    """
    channel_list = list(channels.values())

    if sort_by == SortOption.RELEVANCE:
        return channel_list

    key_funcs = {
        SortOption.MEDIAN_VIEWS: lambda c: c.get('median_views', 0),
        SortOption.SUBSCRIBERS: lambda c: c.get('subscriber_count', 0),
        SortOption.ACTIVITY: lambda c: c.get('last_published') or datetime.min,
    }

    key_func = key_funcs.get(sort_by)
    if key_func is None:
        return channel_list

    # For activity, we want most recent first when descending
    # Handle timezone-naive datetime.min comparison
    if sort_by == SortOption.ACTIVITY:
        def activity_key(c):
            lp = c.get('last_published')
            if lp is None:
                return datetime.min
            # Make timezone-naive for comparison
            if lp.tzinfo is not None:
                return lp.replace(tzinfo=None)
            return lp
        key_func = activity_key

    return sorted(channel_list, key=key_func, reverse=descending)
