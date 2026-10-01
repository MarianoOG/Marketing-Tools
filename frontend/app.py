"""The frontend: one Streamlit app, every tool grouped by section.

Every page talks to the backend MCP server (see :mod:`frontend.client`); none
of them writes to the data folder.

    uv run streamlit run frontend/app.py
"""

import streamlit as st

from frontend.client import BackendError

st.set_page_config(page_title="Marketing Tools", page_icon="🧰", layout="wide")

pages = {
    "Explore": [
        st.Page("pages/explore_search.py", title="Creator Discovery", icon="🔍", default=True),
        st.Page("pages/explore_results.py", title="Results", icon="📊"),
        st.Page("pages/explore_creator.py", title="Creator", icon="👤"),
    ],
    "Create": [
        st.Page("pages/create_library.py", title="Asset Library", icon="🎨"),
        st.Page("pages/create_asset.py", title="Create an asset", icon="✨"),
        st.Page("pages/create_worlds.py", title="Worlds", icon="🌍"),
    ],
}

try:
    st.navigation(pages).run()
except BackendError as exc:
    # Anything a page did not handle itself, most often a backend that is not
    # running: say so instead of showing a traceback.
    st.error(str(exc))
