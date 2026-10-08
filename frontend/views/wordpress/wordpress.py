"""Content Tagging - classify the site's posts, then write categories back.

Two steps, each a background job in the backend:

1. **Analyze** reads the sitemap and classifies every post not classified yet.
2. **Update categories** applies the result to posts still in "Uncategorized".
"""

from __future__ import annotations

from typing import Dict

import pandas as pd
import streamlit as st

import api


def start(path: str) -> bool:
    """Start a job; on refusal show why and stay, so the rerun does not wipe it."""
    try:
        st.session_state.wordpress_job = api.post(path)['id']
    except api.ApiError as exc:
        st.error(str(exc))
        return False
    return True


def count_chart(title: str, counts: Dict[str, int]) -> None:
    st.markdown(f"**{title}**")
    if not counts:
        st.caption("Nothing yet.")
        return
    st.bar_chart(pd.Series(counts, name="Posts"), horizontal=True)


def render_summary() -> None:
    summary = api.get("/wordpress/summary")
    st.subheader("Classified so far")
    if not summary['total']:
        st.info("Nothing classified yet. Run the analysis to start.")
        return

    total_col, teachers_col, keywords_col = st.columns(3)
    total_col.metric("Posts classified", summary['total'])
    teachers_col.metric("Not for teachers", summary['no_para_docentes'])
    keywords_col.metric("Keywords", len(summary['keywords']))

    left, right = st.columns(2)
    with left:
        count_chart("Áreas temáticas", summary['areas_tematicas'])
        count_chart("Satisfacción", summary['satisfaccion'])
    with right:
        count_chart("Niveles educativos", summary['niveles_educativos'])
        count_chart("Dificultad", summary['dificultad'])

    with st.expander("Keywords"):
        st.write(", ".join(summary['keywords']))


def render_result(job: Dict) -> None:
    """The outcome of the last run this session started."""
    if job['status'] == "failed":
        st.error(f"{job['label']} failed: {job['error']}")
        return
    result = job['result']
    if 'updated' in result:
        st.success(f"Updated {len(result['updated'])} posts.")
        if result['failed']:
            st.warning("Failed to update: " + ", ".join(result['failed']))
        st.caption(f"{len(result['without_categories'])} posts have no analysed categories.")
    else:
        st.success(f"Classified {result['processed']} new posts.")
        if result['errors']:
            with st.expander(f"{len(result['errors'])} errors"):
                for error in result['errors']:
                    st.text(error)


@st.fragment(run_every=2)
def watch_job() -> None:
    job = api.get(f"/jobs/{st.session_state.wordpress_job}")
    if job['status'] not in ("queued", "running"):
        st.rerun(scope="app")
        return
    with st.status(f"{job['label']}...", expanded=True):
        for message in job['progress'][-15:]:
            st.write(message)


def main() -> None:
    st.title("🏷️ Content Tagging")
    st.caption(
        "Classify every post on the WordPress site with an LLM, then write the "
        "resulting categories back to the posts that are still uncategorized."
    )

    job = None
    if st.session_state.wordpress_job:
        try:
            job = api.get(f"/jobs/{st.session_state.wordpress_job}")
        except api.ApiError:
            st.session_state.wordpress_job = None
    running = job is not None and job['status'] in ("queued", "running")

    analyze_col, update_col = st.columns(2)
    with analyze_col:
        st.subheader("1. Analyze")
        st.caption("Only posts not classified yet are sent to the model.")
        if st.button("Analyze website", type="primary", disabled=running):
            if start("/wordpress/analyze"):
                st.rerun()
    with update_col:
        st.subheader("2. Update categories")
        st.caption("Writes to the live site. Posts with categories already set are skipped.")
        confirmed = st.checkbox("I want to update the live site", disabled=running)
        if st.button("Update categories", disabled=running or not confirmed):
            if start("/wordpress/update-categories"):
                st.rerun()

    if running:
        watch_job()
    elif job is not None:
        render_result(job)

    st.divider()
    render_summary()


main()
