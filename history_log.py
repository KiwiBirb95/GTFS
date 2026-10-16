from datetime import datetime
import pandas as pd
import streamlit as st

MAX_HISTORY = 20

def init_history(prefix: str):
    if f"{prefix}_history" not in st.session_state:
        st.session_state[f"{prefix}_history"] = []
        st.session_state[f"{prefix}_history_idx"] = -1

def record_change(prefix: str, filename: str, description: str, new_df: pd.DataFrame):
    init_history(prefix)

    tables = st.session_state.get(f"{prefix}_tables", {})
    if filename not in tables:
        return

    current_df = tables[filename]

    if current_df.equals(new_df):
        return

    history = st.session_state[f"{prefix}_history"]
    curr_idx = st.session_state[f"{prefix}_history_idx"]

    if curr_idx < len(history) - 1:
        history = history[: curr_idx + 1]

    entry = {
        "timestamp": datetime.now().strftime("%HH:%MM:%SS"),
        "filename": filename,
        "description": description,
        "prev_df": current_df.copy(),
        "new_df": new_df.copy(),
    }

    history.append(entry)

    if len(history) > MAX_HISTORY:
        history.pop(0)
    else:
        curr_idx += 1

    st.session_state[f"{prefix}_history"] = history
    st.session_state[f"{prefix}_history_idx"] = len(history) - 1

    st.session_state[f"{prefix}_tables"][filename] = new_df

def undo(prefix: str):
    init_history(prefix)
    history = st.session_state[f"{prefix}_history"]
    curr_idx = st.session_state[f"{prefix}_history_idx"]

    if curr_idx >= 0:
        entry = history[curr_idx]
        st.session_state[f"{prefix}_tables"][entry["filename"]] = entry["prev_df"].copy()
        st.session_state[f"{prefix}_history_idx"] = curr_idx - 1
        st.rerun()

def redo(prefix: str):
        init_history(prefix)
        history = st.session_state[f"{prefix}_history"]
        curr_idx = st.session_state[f"{prefix}_history_idx"]

        if curr_idx < len(history) - 1:
            next_idx = curr_idx + 1
            entry = history[next_idx]
            st.session_state[f"{prefix}_tables"][entry["filename"]] = entry["new_df"].copy()
            st.session_state[f"{prefix}_history_idx"] = next_idx
            st.rerun()

def render_history_sidebar():
    with st.sidebar.expander("Change Log & Undo / Redo", expanded=False):
        for pfx in ["feed_a", "feed_b"]:
            tbls = st.session_state.get(f"{pfx}_tables")
            if tbls is not None and not isinstance(tbls, dict):
                st.session_state[f"{pfx}_tables"] = {}
        feed_a_tables = st.session_state.get("feed_a_tables")
        has_a = isinstance(feed_a_tables, dict) and bool(feed_a_tables)
        feed_b_tables = st.session_state.get("feed_b_tables")
        has_b = isinstance(feed_b_tables, dict) and bool(feed_b_tables)
        if not has_a and not has_b:
            st.caption("No GTFS feeds loaded yet.")
            return

        if has_a and has_b:
            target_feed = st.radio("Feed", ["Feed A", "Feed B"], horizontal=True, key="history_feed_choice")
            prefix = "feed_a" if target_feed == "Feed A" else "feed_b"
        elif has_a:
            prefix = "feed_a"
            st.caption("**Feed A Active**")
        else:
            prefix = "feed_b"
            st.caption("**Feed B Active**")

        init_history(prefix)
        history = st.session_state[f"{prefix}_history"]
        curr_idx = st.session_state[f"{prefix}_history_idx"]

        col_u, col_r = st.columns(2)
        can_undo = curr_idx >= 0
        can_redo = curr_idx < len(history) - 1

        if col_u.button("Undo", disabled=not can_undo, width="stretch", key=f"{prefix}_btn_undo"):
            undo(prefix)
        if col_r.button("Redo", disabled=not can_redo, width="stretch", key=f"{prefix}_btn_redo"):
            redo(prefix)

        st.divider()

        if not history:
            st.caption("No changes recorded in this session.")
        else:
            st.markdown(f"**History ({curr_idx + 1}/{len(history)}):**")
            for i, item in enumerate(reversed(history)):
                actual_idx = len(history) - 1 - i
                is_active = actual_idx == curr_idx
                is_undone = actual_idx > curr_idx

                time_str = item["timestamp"]
                desc = item["description"]
                fname = item["filename"]

                if is_undone:
                    st.markdown(f"<span style='color: gray;'>~~`[{time_str}]` **{fname}**: {desc}~~</span>", unsafe_allow_html=True)
                elif is_active:
                    st.markdown(f"**`[{time_str}]` {fname}**: {desc}")
                else:
                    st.markdown(f"&bull; `[{time_str}]` {fname}**: {desc}")

