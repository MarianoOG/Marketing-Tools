"""WordPress content tagging: classify every post with an LLM, then write the
resulting categories back to the site.

Both steps share their files under ``<DATA_DIR>/wordpress/``:

- ``metadata.jsonl``        one classification per post, appended to
- ``errors.txt``            the last analysis run's failures
- ``url_to_categories.json`` the categories the update step applies
"""

from __future__ import annotations

import os

from app.settings import WORDPRESS_DIR

METADATA_FILE = WORDPRESS_DIR / "metadata.jsonl"
ERRORS_FILE = WORDPRESS_DIR / "errors.txt"
CATEGORIES_FILE = WORDPRESS_DIR / "url_to_categories.json"


def get_setting(name: str) -> str:
    """Read a required setting from the environment, failing loudly if unset."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Add it to backend/.env.")
    return value
