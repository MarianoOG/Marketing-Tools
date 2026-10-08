"""
Creator Discovery - Audience Insights
Turn the comments of a search's most-discussed videos into content ideas.

The estimate is free and refreshes with the controls; Run starts a background
job in the backend, and the finished run is saved there and reopened from
"Previous runs".
"""

from datetime import datetime
from typing import Dict, Optional

import pandas as pd
import streamlit as st

import api
from shared.youtube import RESULTS_PAGE, adopt_from_url


def render_controls(search_id: str, keyword: str, channel_id: Optional[str]) -> Dict:
    """Scope, video count, comments per video and language. Returns the run settings."""
    options = api.options("youtube")
    scopes = {None: f'All creators for "{keyword}"'}
    if channel_id:
        channel = api.get(f"/youtube/searches/{search_id}/channels/{channel_id}")
        scopes[channel_id] = channel['channel_name']

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    scope = col1.selectbox("Scope", list(scopes), format_func=scopes.get, index=len(scopes) - 1)
    videos = col2.number_input(
        "Videos", min_value=1, max_value=options['insight_videos']['max'],
        value=options['insight_videos']['default'],
        help="The most-commented videos are read first",
    )
    per_video = col3.selectbox(
        "Comments per video", options['comments_per_video'],
        index=options['comments_per_video'].index(options['default_comments_per_video']),
    )
    language = col4.text_input("Output language", value="English", help="Quotes stay in their original language")
    return {'channel_id': scope, 'videos': int(videos), 'per_video': per_video, 'language': language}


def render_estimate(search_id: str, settings: Dict) -> Dict:
    estimate = api.get(
        f"/youtube/searches/{search_id}/insights/estimate",
        channel_id=settings['channel_id'], videos=settings['videos'], per_video=settings['per_video'],
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Videos", len(estimate['videos']))
    col2.metric("YouTube quota", f"≤ {estimate['quota_units']} units")
    col3.metric("LLM tokens", f"~{estimate['input_tokens'] + estimate['output_tokens']:,}")
    col4.metric("LLM cost", f"~${estimate['cost_usd']:.3f}")
    caption = f"Analysis with {estimate['model']}."
    if estimate['per_channel_cap']:
        caption += f" At most {estimate['per_channel_cap']} videos per creator."
    st.caption(caption)
    if not estimate['analysis_available']:
        st.warning("OPENAI_API_KEY is not set in backend/.env: the run will fetch the comments "
                   "but skip the analysis.")
    with st.expander("Videos to read"):
        st.dataframe(
            pd.DataFrame(estimate['videos']),
            column_order=['title', 'channel_name', 'comment_count', 'url'],
            column_config={
                'title': st.column_config.TextColumn('Title', width='large'),
                'channel_name': 'Channel',
                'comment_count': st.column_config.NumberColumn('Comments', format='%d'),
                'url': st.column_config.LinkColumn('Link', display_text='Watch'),
            },
            hide_index=True,
            width='stretch',
        )
    return estimate


def start_run(search_id: str, settings: Dict) -> None:
    try:
        job = api.post(f"/youtube/searches/{search_id}/insights", json=settings)
        st.session_state.insights_job = job['id']
        st.session_state.insights_error = None
    except api.ApiError as exc:
        st.session_state.insights_error = str(exc)


@st.fragment(run_every=1)
def watch_run() -> None:
    """Stream the job's progress messages; hand over to ``main`` when it ends."""
    job = api.get(f"/jobs/{st.session_state.insights_job}")
    if job['status'] not in ("queued", "running"):
        st.rerun(scope="app")
        return
    with st.status("Mining comments...", expanded=True):
        for message in job['progress']:
            st.write(message)


def finish_run() -> None:
    try:
        job = api.get(f"/jobs/{st.session_state.insights_job}")
    except api.ApiError as exc:
        st.session_state.insights_job = None
        st.session_state.insights_error = str(exc)
        return
    if job['status'] in ("queued", "running"):
        return
    st.session_state.insights_job = None
    if job['status'] == "failed":
        st.session_state.insights_error = job['error']
    else:
        st.session_state.insights_id = job['result']['insights_id']


def render_previous_runs(search_id: str) -> None:
    runs = api.get("/youtube/insights", search_id=search_id)
    if not runs:
        return
    labels = {
        run['id']: (
            f"{run['channel_name'] or 'All creators'} · {run['ideas']} ideas · {run['comments']} comments · "
            f"{datetime.fromisoformat(run['created_at']).strftime('%b %d, %Y %H:%M')}"
        )
        for run in runs
    }
    choice_col, open_col = st.columns([4, 1])
    chosen = choice_col.selectbox("Previous runs", list(labels), format_func=labels.get)
    open_col.write("")
    if open_col.button("Open", width='stretch'):
        st.session_state.insights_id = chosen
        st.rerun()


def render_insights(view: Dict) -> None:
    st.subheader(f"Insights: {view['scope_label']}")
    st.caption(f"{len(view['comments'])} comments from {len(view['videos'])} videos")
    if view['note']:
        st.info(view['note'])

    if view['ideas']:
        st.markdown("### Content ideas")
        for i, idea in enumerate(view['ideas'], start=1):
            with st.container(border=True):
                st.markdown(f"**{i}. {idea['title']}**")
                st.write(idea['angle'])
                st.caption(f"Answers: {', '.join(idea['themes'])}")
                st.markdown(f"*Why it should work:* {idea['evidence']}")

    if view['theme_groups']:
        st.markdown("### Themes")
        tabs = st.tabs([group['label'] for group in view['theme_groups']])
        for tab, group in zip(tabs, view['theme_groups']):
            with tab:
                for theme in group['themes']:
                    st.markdown(f"**{theme['label']}** - {theme['summary']}")
                    for quote in theme['quotes']:
                        st.markdown(f"> {quote}")
                    if theme['videos']:
                        st.caption(" · ".join(f"[{v['title']}]({v['url']})" for v in theme['videos']))
                    st.write("")

    comments = pd.DataFrame(view['comments'])
    with st.expander(f"Comments ({len(comments)})"):
        if comments.empty:
            st.info("No comments.")
        else:
            st.dataframe(
                comments,
                column_order=['text', 'likes', 'replies', 'author', 'video_title', 'video_url'],
                column_config={
                    'text': st.column_config.TextColumn('Comment', width='large'),
                    'likes': st.column_config.NumberColumn('Likes', format='%d'),
                    'replies': st.column_config.NumberColumn('Replies', format='%d'),
                    'author': 'Author',
                    'video_title': 'Video',
                    'video_url': st.column_config.LinkColumn('Link', display_text='Watch'),
                },
                hide_index=True,
                width='stretch',
            )

    col1, col2 = st.columns(2)
    col1.download_button(
        "Download insights (Markdown)", view['markdown'],
        file_name=f"{view['id']}.md", mime="text/markdown", width='stretch',
    )
    col2.download_button(
        "Download comments (CSV)", comments.to_csv(index=False),
        file_name=f"{view['id']}_comments.csv", mime="text/csv", width='stretch',
        disabled=comments.empty,
    )


def main():
    """Audience Insights page."""
    search_id = adopt_from_url('search_id', 'search')
    if not search_id:
        st.warning("No search selected. Run or open a search first.")
        if st.button("Go to Results"):
            st.switch_page(RESULTS_PAGE)
        return
    channel_id = adopt_from_url('insights_channel', 'scope')

    if st.session_state.insights_job:
        finish_run()

    try:
        results = api.get(f"/youtube/searches/{search_id}/channels")
    except api.ApiError as exc:
        st.error(str(exc))
        return

    st.title("Audience Insights")
    st.caption("What viewers ask, complain about, request and praise, turned into content ideas.")
    if st.button("← Back to Results"):
        st.switch_page(RESULTS_PAGE)

    settings = render_controls(search_id, results['keyword'], channel_id)
    estimate = render_estimate(search_id, settings)

    running = bool(st.session_state.insights_job)
    if st.button("Run", type="primary", disabled=running or not estimate['videos']):
        start_run(search_id, settings)
        st.rerun()
    if st.session_state.insights_job:
        watch_run()
    if st.session_state.insights_error:
        st.error(st.session_state.insights_error)

    st.divider()
    render_previous_runs(search_id)

    if st.session_state.insights_id:
        try:
            view = api.get(f"/youtube/insights/{st.session_state.insights_id}")
        except api.ApiError as exc:
            st.error(str(exc))
            return
        render_insights(view)


main()
