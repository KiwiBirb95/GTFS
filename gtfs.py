import os
import sys

if sys.platform == "win32":
    from asyncio.proactor_events import _ProactorBasePipeTransport

    _orig_call_connection_lost = (
        _ProactorBasePipeTransport._call_connection_lost
    )

    def _call_connection_lost_silenced(self, exc=None):
        try:
            _orig_call_connection_lost(self, exc)
        except (ConnectionResetError, OSError):
            pass

    _ProactorBasePipeTransport._call_connection_lost = (
        _call_connection_lost_silenced
    )
    
from pathlib import Path
import streamlit as st

from gtfs_utils import load_gtfs_tables, create_gtfs_zip, pick_folder, reload_single_table
from map_view import render_dual_gtfs_map
from validator import render_validator_ui
from diff_view import render_diff_view
from text_diff_view import render_text_diff_view

st.set_page_config(
    page_title="GTFS Feed Editor",
    page_icon="🚃",
    layout='wide'
)

st.title("GTFS Feed Editor")

for pfx in ["feed_a", "feed_b"]:
    if f"{pfx}_tables" not in st.session_state:
        st.session_state[f"{pfx}_tables"] = {}

    if f"{pfx}_current_key" not in st.session_state:
        st.session_state[f"{pfx}_current_key"] = None

    if f"{pfx}_active_source" not in st.session_state:
        st.session_state[f"{pfx}_active_source"] = None

PRIORITY_ORDER = [
    "agency.txt", "routes.txt", "trips.txt", "stop_times.txt",
    "stops.txt", "calendar.txt", "calendar_dates.txt", "shapes.txt",
    "frequencies.txt", "transfers.txt", "feed_info.txt"
]

def handle_source_ingestion(prefix, title_label):
    st.subheader(title_label)

    # source_type = st.radio(
    #     f"Select GTFS Source ({title_label}):",
    #     ["Upload GTFS .zip", "Open Unzipped Folder"],
    #     horizontal = True,
    #     key=f"{prefix}_source_type_radio"
    # )

    source_type = st.radio(
        f"Select GTFS Source ({title_label}):",
        ["Upload GTFS .zip"],
        horizontal = True,
        key=f"{prefix}_source_type_radio"
    )

    new_file_key = None
    new_source = None

    if source_type == "Upload GTFS .zip":
        uploaded_zip = st.file_uploader(
            "Choose a GTFS ZIP file",
            type=["zip"],
            key=f"{prefix}_uploader",
            help="Upload your gtfs.zip file containing standard GTFS files"
        )
        if uploaded_zip is not None:
            new_file_key = f"file_{uploaded_zip.name}_{uploaded_zip.size}"
            new_source = uploaded_zip
        else:
            if st.session_state[f"{prefix}_current_key"] and str(st.session_state[f"{prefix}_current_key"]).startswith("zip_"):
                st.session_state[f"{prefix}_tables"] = {}
                st.session_state[f"{prefix}_current_key"] = None
                st.session_state[f"{prefix}_active_source"] = None
                st.session_state.pop(f"{prefix}_validation_executed", None)
    # else:
    #     col_btn, col_path = st.columns([1, 4], vertical_alignment="center")
    #     with col_btn:
    #         if st.button("Browse Folder...", key=f"{prefix}_btn_browse", width="stretch"):
    #             chosen = pick_folder()
    #             if chosen:
    #                 st.session_state[f"{prefix}_selected_folder"] = chosen
    #                 st.rerun()

    #     selected_dir = st.session_state.get(f"{prefix}_selected_folder", "")
    #     with col_path:
    #         if selected_dir:
    #             st.code(selected_dir, language="text")
    #         else:
    #             st.caption("No folder selected yet. Click 'Browse Folder' to select an unzipped GTFS folder.")

    #     if selected_dir and os.path.isdir(selected_dir):
    #         new_file_key = f"folder_{os.path.abspath(selected_dir)}"
    #         new_source = selected_dir
    #     else:
    #         if st.session_state[f"{prefix}_current_key"] and str(st.session_state[f"{prefix}_current_key"]).startswith("folder_"):
    #             st.session_state[f"{prefix}_tables"] = {}
    #             st.session_state[f"{prefix}_current_key"] = None
    #             st.session_state[f"{prefix}_active_source"] = None
    #             st.session_state.pop(f"{prefix}_validation_executed", None)

    if new_file_key and (st.session_state[f"{prefix}_current_key"] != new_file_key):
        with st.spinner(f"Extracting and parsing GTFS tables for {title_label}..."):
            loaded = load_gtfs_tables(new_source)
            if loaded:
                st.session_state[f"{prefix}_tables"] = loaded
                st.session_state[f"{prefix}_current_key"] = new_file_key
                st.session_state[f"{prefix}_active_source"] = new_source
                st.rerun()
            else:
                st.error(f"No valid .txt tables found in {title_label}.")

def render_feed_editor(prefix, title_label):
    tables = st.session_state.get(f"{prefix}_tables", {})

    if tables:
        sorted_filenames = sorted(
            tables.keys(),
            key=lambda x: (PRIORITY_ORDER.index(x) if x in PRIORITY_ORDER else 999, x)
        )

        st.caption(f"Loaded **{len(sorted_filenames)}** GTFS files.")
        st.divider()

        render_validator_ui(
            jar_path="gtfs-validator-8.0.1-cli.jar",
            tables_dict=tables,
            create_gtfs_zip_fn=create_gtfs_zip,
            key_prefix=prefix)
        
        st.divider()

        tabs = st.tabs(sorted_filenames)

        for tab, filename in zip(tabs, sorted_filenames):
            with tab:
                df = tables[filename]

                c_info, c_select, c_clear, c_reset = st.columns(
                    [3.2, 2.0, 1.3, 1.0],
                    vertical_alignment="center"
                )

                with c_info:
                    st.markdown(
                        f"<span style='color: gray; font-size: 0.875rem;'><code>{filename}</code> &mdash; {len(df):,} rows &times; {len(df.columns)} cols</span>",
                        unsafe_allow_html=True
                    )

                with c_select:
                    target_col = st.selectbox(
                        "Select column to clear",
                        options=df.columns.tolist(),
                        key=f"{prefix}_col_select_{filename}",
                        label_visibility="collapsed"
                    )

                with c_clear:
                    if st.button(
                        "Clear Data",
                        key=f"{prefix}_clear_{filename}",
                        width='stretch',
                        help=f"Wipe values in '{target_col}' to empty while preserving the header row"
                    ):
                        st.session_state[f"{prefix}_tables"][filename][target_col] = ""
                        st.rerun()

                with c_reset:
                    if st.button(
                        "Reset",
                        key=f"{prefix}_reset_{filename}",
                        width="stretch",
                        help="Revert this table to its original uploaded state"
                    ):
                        st.session_state[f"{prefix}_tables"][filename] = reload_single_table(
                            st.session_state[f"{prefix}_active_source"],
                            filename
                        )
                        st.rerun()

                edited_df = st.data_editor(
                    st.session_state[f"{prefix}_tables"][filename],
                    key = f"{prefix}_editor_{filename}",
                    num_rows="dynamic",
                    width='stretch',
                    height=520
                )
                if f"{prefix}_tables" in st.session_state:
                    st.session_state[f"{prefix}_tables"][filename] = edited_df
        st.divider()
        zip_output = create_gtfs_zip(st.session_state.get(f"{prefix}_tables", tables))
        source_ref = st.session_state.get(f"{prefix}_active_source")
        if isinstance(source_ref, (str, Path)):
            base_name = Path(source_ref).name
        elif hasattr(source_ref, "name") and source_ref.name:
            base_name = source_ref.name.rsplit(".", 1)[0]
        else:
            base_name = f"{prefix}_gtfs_feed"
        st.download_button(
            label=f"Download Updated GTFS ZIP ({prefix.upper()})",
            data=zip_output,
            file_name=f"{base_name}_modified.zip",
            mime="application/zip",
            type="primary",
            key=f"{prefix}_dl_btn",
            width="stretch"
        )
    else:
        st.info(f"Please load a GTFS feed for {title_label} above.")

load_col_a, load_col_b = st.columns(2)
with load_col_a:
    handle_source_ingestion(prefix="feed_a", title_label="Feed A")
with load_col_b:
    handle_source_ingestion(prefix="feed_b", title_label="Feed B")

st.divider()

tables_a = st.session_state.get("feed_a_tables", {})
tables_b = st.session_state.get("feed_b_tables", {})

render_dual_gtfs_map(tables_a, tables_b, height=800)

if tables_a and tables_b:
    st.divider()
    with st.expander(
        "GTFS Feed Diff Comparison (Side-by-Side)", expanded=True
    ):
        diff_tab1, diff_tab2 = st.tabs(
            ["Table Grid Diff", "Git-Style Diff (st-diff-viewer)"]
        )
        with diff_tab1:
            render_diff_view(
                tables_a, tables_b, name_a="Feed A", name_b="Feed B"
            )
        with diff_tab2:
            render_text_diff_view(
                tables_a, tables_b, name_a="Feed A", name_b="Feed B"
            )

st.divider()

col_a, col_b = st.columns(2)
with col_a:
    render_feed_editor(prefix="feed_a", title_label="Feed A")

with col_b:
    render_feed_editor(prefix="feed_b", title_label="Feed B")