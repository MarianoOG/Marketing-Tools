"""Worlds - create, rename and delete the settings assets are grouped into.

Switching worlds happens in the sidebar on every page; this page is only for
changing the set of them. Rename and delete are held while a generation is in
flight: a pool thread may be about to write into the folder being touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import jobs
from shared.library import list_assets
from shared.state import init_session_state
from shared.worlds import (
    create_world,
    delete_world,
    list_worlds,
    render_world_switcher,
    rename_world,
)


def notify(kind: str, text: str) -> None:
    """Report through session state: the rerun below wipes the page first."""
    st.session_state.bulk_notice = (kind, text)
    list_assets.clear()
    st.rerun()


def render_create() -> None:
    """Name a new world and switch to it. Safe to do mid-generation: a new,
    empty folder cannot disturb a render already writing elsewhere."""
    st.subheader("New world")
    name_col, button_col = st.columns([3, 1])
    name = name_col.text_input(
        "World name",
        placeholder="night_market",
        label_visibility='collapsed',
        key='new_world_name',
    )
    if button_col.button("Create", type="primary", width='stretch'):
        try:
            st.session_state.current_world = create_world(name)
        except ValueError as exc:
            st.error(str(exc))
            return
        notify('success', f"Created **{st.session_state.current_world}**.")


def render_world_row(world: str, active: bool, disabled: bool) -> None:
    """One world: its size, a rename, and a delete behind a confirmation."""
    count = len(list_assets(world=world))
    heading = f"### {world}" + ("  ·  *active*" if active else "")
    st.markdown(heading)
    st.caption(f"{count} asset{'s' if count != 1 else ''}")

    rename_col, delete_col = st.columns(2)

    with rename_col:
        new_name = st.text_input(
            "Rename to",
            value=world,
            key=f"rename_{world}",
            disabled=disabled,
        )
        if st.button("Rename", key=f"rename_button_{world}", disabled=disabled):
            try:
                renamed = rename_world(world, new_name)
            except ValueError as exc:
                st.error(str(exc))
                return
            if active:
                st.session_state.current_world = renamed
            notify('success', f"Renamed **{world}** to **{renamed}**.")

    with delete_col:
        st.caption(
            f"Deletes {world} and its {count} asset{'s' if count != 1 else ''}. "
            "This cannot be undone - img/ is not tracked by git."
        )
        confirmed = st.checkbox(
            "Confirm delete", key=f"confirm_world_{world}", disabled=disabled
        )
        if st.button(
            "Delete",
            type="primary",
            key=f"delete_world_{world}",
            disabled=disabled or not confirmed,
        ):
            try:
                delete_world(world)
            except ValueError as exc:
                st.error(str(exc))
                return
            if active:
                # The switcher reconciles ``current_world`` against disk, but the
                # selection belongs to the world that just went away.
                st.session_state.selection = set()
                st.session_state.current_world = list_worlds()[0]
            notify('success', f"Deleted **{world}**.")


def main() -> None:
    st.set_page_config(page_title="Worlds - Asset Library", page_icon="🌍", layout="wide")
    init_session_state()
    jobs.collect()

    busy = bool(jobs.running_count())
    active = render_world_switcher(disabled=busy, link=False)

    st.title("🌍 Worlds")
    st.caption(
        "A world owns its own characters, objects, locations and scenes. A scene "
        "can only be built from references in its own world."
    )

    if st.session_state.bulk_notice:
        kind, text = st.session_state.bulk_notice
        getattr(st, kind)(text)
        st.session_state.bulk_notice = None

    if st.button("← Back to library"):
        st.switch_page("Home.py")

    if busy:
        st.info("A generation is running. Renaming and deleting are held until it lands.")

    st.divider()
    render_create()

    for world in list_worlds():
        st.divider()
        render_world_row(world, world == active, busy)


if __name__ == '__main__':
    main()
