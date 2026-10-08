"""
Configuration and Presets

Central configuration for the Creator Discovery service.
All tunable values and filter presets are defined here.
"""

import logging

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

MAX_RESULTS_PER_KEYWORD = 1000
OUTPUT_FILE = "creators.jsonl"
MIN_VIEWS = 100
MAX_VIEWS = 1000
MIN_CHANNEL_VIDEOS = 5
MAX_CHANNEL_VIDEOS = 100
MIN_SUBSCRIBERS = 100
MAX_SUBSCRIBERS = 10000
BATCH_SIZE = 50  # Max channel IDs per batch request

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

# ============================================================================
# AUDIENCE INSIGHTS (comment mining)
# ============================================================================

#: Inexpensive OpenAI model with structured outputs, and its USD price per 1M
#: tokens (input, output) for the pre-run estimate.
INSIGHTS_MODEL = "gpt-6-luna"
INSIGHTS_PRICE_PER_M = (0.10, 0.50)

COMMENTS_PAGE_SIZE = 100  # commentThreads.list max; one page costs 1 quota unit
DEFAULT_INSIGHT_VIDEOS = 20
MAX_INSIGHT_VIDEOS = 50
DEFAULT_COMMENTS_PER_VIDEO = 200
COMMENTS_PER_VIDEO_OPTIONS = [100, 200, 300, 500]
#: Niche scope only - keeps one big creator from speaking for the whole niche.
MAX_VIDEOS_PER_CHANNEL = 3
#: Comments past this many input tokens are dropped, lowest-liked first.
INSIGHTS_TOKEN_BUDGET = 100_000
#: Rough sizes for the estimate, before any comment has been fetched.
EST_TOKENS_PER_COMMENT = 35
EST_OUTPUT_TOKENS = 4_000

INSIGHT_CATEGORIES = {
    "request": "Requests",
    "question": "Questions",
    "pain_point": "Pain points",
    "praise": "Praise",
}

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
