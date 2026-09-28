import duckdb
import pandas as pd
import streamlit as st

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

def normalize_key_value(val, col_name):
    s = str(val).strip()
    if "time" in col_name and ":" in s:
        parts = s.split(":")
        if len(parts) == 3 and len(parts[0]) == 1:
            return f"0{parts[0]}:{parts[1]}:{parts[2]}"
    return s

def compute_table_diff_duckdb(df_a, df_b, filename):
    cols_a = list (df_a.columns)
    cols_b = list (df_b.columns)

    added_cols = [c for c in cols_b if c not in cols_a]
    removed_cols = [c for c in cols_a if c not in cols_b]
    common_cols = [c for c in cols_a if c in cols_b]

    default_keys = GTFS_PRIMARY_KEYS.get(filename, [])
    keys = [k for k in default_keys if k in common_cols]
    if not keys:
        keys = [common_cols[0]] if common_cols else []

    if not keys:
        return None, None, None, None, {"error": f"No common columns to join `{filename}`."}

    a_df = df_a.copy()
    b_df = df_b.copy()
    for k in keys:
        a_df[k] = a_df[k].apply(lambda v: normalize_key_value(v, k))
        b_df[k] = b_df[k].apply(lambda v: normalize_key_value(v, k))

    compare_cols = [c for c in common_cols if c not in keys]

    con = duckdb.connect(database=":memory:")
    con.register("tbl_a", a_df)
    con.register("tbl_b", b_df)

    join_cond = " AND ".join([f'a."{k}" = b."{k}"' for k in keys])
    key_selects = ", ".join(
        [f'COALESCE(a."{k}", b."{k}") AS "{k}"' for k in keys]
    )

    if compare_cols:
        distinct_checks = [
            f'a."{c}" IS DISTINCT FROM b."{c}"' for c in compare_cols
        ]
        mod_cond = " OR ".join(distinct_checks)
        status_sql = f"""
            CASE
                WHEN b."{keys[0]}" IS NULL THEN 'REMOVED'
                WHEN a."{keys[0]}" IS NULL THEN 'ADDED'
                WHEN ({mod_cond}) THEN 'MODIFIED'
                ELSE 'UNCHANGED'
            END AS _diff_status
        """
    else:
        status_sql = f"""
            CASE
                WHEN b."{keys[0]}" IS NULL THEN 'REMOVED'
                WHEN a."{keys[0]}" IS NULL THEN 'ADDED'
                ELSE 'UNCHANGED'
            END AS _diff_status
        """

    a_cols_sql = [f'a."{c}" AS "a_{c}"' for c in a_df.columns if c not in keys]
    b_cols_sql = [f'b."{c}" AS "b_{c}"' for c in b_df.columns if c not in keys]
    all_col_selects = ", ".join(a_cols_sql + b_cols_sql)
    extra_str = f", {all_col_selects}" if all_col_selects else ""

    query = f"""
        SELECT
            {key_selects},
            {status_sql}
            {extra_str}
        FROM tbl_a a
        FULL OUTER JOIN tbl_b b ON {join_cond}
        ORDER BY {', '.join([f'"{k}"' for k in keys])}
    """

    merged_df = con.execute(query).df()
    con.close()

    counts = merged_df["_diff_status"].value_counts().to_dict()
    summary = {
        "keys": keys,
        "added": counts.get("ADDED", 0),
        "removed": counts.get("REMOVED", 0),
        "modified": counts.get("MODIFIED", 0),
        "unchanged": counts.get("UNCHANGED", 0),
        "added_cols": added_cols,
        "removed_cols": removed_cols,
        "common_cols": common_cols,
        "compare_cols": compare_cols,
    }

    return merged_df, a_df, b_df, summary, None

def render_diff_view(tables_a, tables_b, name_a="Feed A", name_b="Feed B"):
    st.subheader(f"GTFS Cross-Feed Comparison: `{name_a}` vs `{name_b}`")

    all_files = sorted(list(set(tables_a.keys()).union(set(tables_b.keys()))))
    priority = [
        "routes.txt",
        "trips.txt",
        "stops.txt",
        "stop_times.txt",
        "calendar.txt"
    ]
    all_files = sorted(all_files, key=lambda x: (priority.index(x) if x in priority else 999, x))

    c_sel, c_filter = st.columns([1.5, 2.5], vertical_alignment="center")

    with c_sel:
        selected_file = st.selectbox(
            "Select GTFS Table to Compare:",
            all_files,
            key="diff_selected_file"
        )

    in_a = selected_file in tables_a
    in_b = selected_file in tables_b

    if not in_a:
        st.warning(
            f"`{selected_file}` is missing from **{name_a}** (All rows added in"
            f" {name_b})."
        )
        st.dataframe(tables_b[selected_file], width='stretch')
        return
    if not in_b:
        st.warning(
            f"`{selected_file}` is missing from **{name_b}** (All rows removed"
            f" in {name_b})."
        )
        st.dataframe(tables_a[selected_file], width='stretch')
        return

    merged_df, df_a, df_b, summary, err = compute_table_diff_duckdb(
        tables_a[selected_file], tables_b[selected_file], selected_file
    )

    if err:
        st.error(err["error"])
        return

    with c_filter:
        diff_filter = st.radio(
            "Filter Rows:",
            [
                "All Rows",
                "Only Diffs (Added / Removed / Modified)",
                "Modified Only",
                "Added / Removed Only",
            ],
            horizontal=True,
            key="diff_filter_mode"
        )

    added_cols = summary["added_cols"]
    removed_cols = summary["removed_cols"]
    if added_cols or removed_cols:
        col_notes = []
        if added_cols:
            col_notes.append(
                f"🟢 **{len(added_cols)} Column(s) Added in {name_b}**: `{', '.join(added_cols)}`"
            )
        if removed_cols:
            col_notes.append(
                f"🔴 **{len(removed_cols)} Column(s) Missing in {name_b}**: `{', '.join(removed_cols)}`"
            )
        st.info(" | ".join(col_notes))
    
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Keys Used", ", ".join(summary["keys"]))
    m2.metric("🟢 Added Rows", summary["added"])
    m3.metric("🔴 Removed Rows", summary["removed"])
    m4.metric("🟡 Modified Rows", summary["modified"])
    m5.metric("⚪ Unchanged", summary["unchanged"])

    st.markdown(
        """
        <div style='display: flex; gap: 15px; margin-bottom: 10px; font-size: 0.85rem;'>
            <span><span style='background: rgba(46, 139, 87, 0.3); padding: 2px 8px; border-radius: 4px;'>&nbsp;</span> Added</span>
            <span><span style='background: rgba(255, 99, 71, 0.3); padding: 2px 8px; border-radius: 4px;'>&nbsp;</span> Removed</span>
            <span><span style='background: rgba(255, 215, 0, 0.45); padding: 2px 8px; border-radius: 4px;'>&nbsp;</span> Value Modified</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    if diff_filter == "Only Diffs (Added / Removed / Modified)":
        display_df = merged_df[
            merged_df["_diff_status"].isin(["ADDED", "REMOVED", "MODIFIED"])
        ]
    elif diff_filter == "Modified Only":
        display_df = merged_df[merged_df["_diff_status"] == "MODIFIED"]
    elif diff_filter == "Added / Removed Only":
        display_df = merged_df[
            merged_df["_diff_status"].isin(["ADDED", "REMOVED"])
        ]
    else:
        display_df = merged_df

    keys = summary["keys"]
    compare_cols = summary["compare_cols"]

    a_cols_orig = [c for c in df_a.columns if c not in keys]
    b_cols_orig = [c for c in df_b.columns if c not in keys]

    slice_a = display_df[keys].copy()
    for c in a_cols_orig:
        slice_a[c] = display_df[f"a_{c}"].fillna("— [Not in Feed A] —")

    slice_b = display_df[keys].copy()
    for c in b_cols_orig:
        slice_b[c] = display_df[f"b_{c}"].fillna("— [Removed in Feed B] —")

    status = display_df["_diff_status"].values

    def get_styles_a(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, st_val in enumerate(status):
            if st_val == "REMOVED":
                styles.iloc[i, :] = (
                    "background-color: rgba(255, 99, 71, 0.25); color: #b22222;"
                    " font-weight: bold;"
                )
            elif st_val == "ADDED":
                styles.iloc[i, :] = (
                    "background-color: rgba(240, 240, 240, 0.5); color:"
                    " #888888; font-style: italic;"
                )
            elif st_val == "MODIFIED":
                for col in compare_cols:
                    if col in df.columns:
                        val_a = display_df[f"a_{col}"].iloc[i]
                        val_b = display_df[f"b_{col}"].iloc[i]
                        if val_a != val_b:
                            styles.iloc[i, df.columns.get_loc(col)] = (
                                "background-color: rgba(255, 215, 0, 0.5);"
                                " font-weight: bold;"
                            )
        return styles

    def get_styles_b(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, st_val in enumerate(status):
            if st_val == "ADDED":
                styles.iloc[i, :] = (
                    "background-color: rgba(46, 139, 87, 0.25); color: #2e8b57;"
                    " font-weight: bold;"
                )
            elif st_val == "REMOVED":
                styles.iloc[i, :] = (
                    "background-color: rgba(240, 240, 240, 0.5); color:"
                    " #888888; font-style: italic;"
                )
            elif st_val == "MODIFIED":
                for col in compare_cols:
                    if col in df.columns:
                        val_a = display_df[f"a_{col}"].iloc[i]
                        val_b = display_df[f"b_{col}"].iloc[i]
                        if val_a != val_b:
                            styles.iloc[i, df.columns.get_loc(col)] = (
                                "background-color: rgba(255, 215, 0, 0.5);"
                                " font-weight: bold;"
                            )
        return styles

    styled_a = slice_a.style.apply(get_styles_a, axis=None)
    styled_b = slice_b.style.apply(get_styles_b, axis=None)

    left_col, right_col = st.columns(2)

    with left_col:
        st.markdown(
            f"**{name_a}** &mdash; Showing `{len(slice_a):,}` aligned rows"
        )
        st.dataframe(styled_a, width="stretch", height=600)

    with right_col:
        st.markdown(
            f"**{name_b}** &mdash; Showing `{len(slice_b):,}` aligned rows"
        )
        st.dataframe(styled_b, width="stretch", height=600)