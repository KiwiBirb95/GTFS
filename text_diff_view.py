import pandas as pd
import streamlit as st

try:
    from st_diff_viewer import diff_viewer

    DIFF_VIEWER_AVAILABLE = True
except ImportError:
    DIFF_VIEWER_AVAILABLE = False

GTFS_PRIMARY_KEYS = {
    "agency.txt": ["agency_id"],
    "routes.txt": ["route_id"],
    "trips.txt": ["trip_id"],
    "stops.txt": ["stop_id"],
    "stop_times.txt": ["trip_id", "stop_sequence"],
    "calendar.txt": ["service_id"],
    "calendar_dates.txt": ["service_id", "date"],
    "shapes.txt": ["shape_id", "shape_pt_sequence"],
    "frequencies.txt": ["trip_id", "start_time"],
    "transfers.txt": ["from_stop_id", "to_stop_id"],
    "feed_info.txt": ["feed_publisher_name"],
}


def render_text_diff_view(
    tables_a, tables_b, name_a="Feed A", name_b="Feed B"
):
    st.subheader(f"Git-Style Text Diff: `{name_a}` vs `{name_b}`")

    if not DIFF_VIEWER_AVAILABLE:
        st.error(
            "The package `st-diff-viewer` is not installed. Please run `pip"
            " install st-diff-viewer` in your terminal and restart the app."
        )
        return

    all_files = sorted(list(set(tables_a.keys()).union(set(tables_b.keys()))))
    priority = [
        "routes.txt",
        "trips.txt",
        "stops.txt",
        "stop_times.txt",
        "calendar.txt",
    ]
    all_files = sorted(
        all_files, key=lambda x: (priority.index(x) if x in priority else 999, x)
    )

    c_file, c_split, c_limit = st.columns([1.5, 1.2, 1.3])

    with c_file:
        selected_file = st.selectbox(
            "Select Table:", all_files, key="text_diff_selected_file"
        )

    with c_split:
        view_mode = st.radio(
            "Diff Layout:",
            ["Split (Side-by-Side)", "Unified (Inline)"],
            horizontal=True,
            key="text_diff_layout",
        )
        split_view = view_mode == "Split (Side-by-Side)"

    with c_limit:
        max_rows = st.select_slider(
            "Max Rows to Compare:",
            options=[100, 500, 1000, 5000, "All"],
            value=500,
            help="Limits rows passed into the viewer to prevent browser lag on massive tables like stop_times.txt.",
            key="text_diff_max_rows",
        )

    in_a = selected_file in tables_a
    in_b = selected_file in tables_b

    if not in_a:
        st.warning(
            f"`{selected_file}` is missing from **{name_a}** (All rows added in"
            f" {name_b})."
        )
        old_text = ""
        new_text = tables_b[selected_file].to_csv(index=False)
    elif not in_b:
        st.warning(
            f"`{selected_file}` is missing from **{name_b}** (All rows removed"
            f" in {name_b})."
        )
        old_text = tables_a[selected_file].to_csv(index=False)
        new_text = ""
    else:
        df_a = tables_a[selected_file].copy()
        df_b = tables_b[selected_file].copy()

        sort_keys = [
            k
            for k in GTFS_PRIMARY_KEYS.get(selected_file, [])
            if k in df_a.columns and k in df_b.columns
        ]
        if sort_keys:
            df_a = df_a.sort_values(by=sort_keys)
            df_b = df_b.sort_values(by=sort_keys)

        if max_rows != "All":
            df_a = df_a.head(max_rows)
            df_b = df_b.head(max_rows)

        old_text = df_a.to_csv(index=False)
        new_text = df_b.to_csv(index=False)

    diff_viewer(old_text=old_text, new_text=new_text, split_view=split_view)