import io
import zipfile
from pathlib import Path
import pandas as pd
import streamlit as st
from history_log import record_change

def pick_folder():
    try:

        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        folder_selected = filedialog.askdirectory()
        root.destroy()
        return folder_selected
    except Exception:
        st.warning(
            "Folder browsing is only supported when running locally on your"
            " desktop. On web deployments, please upload a .zip file."
        )
        return None

def load_gtfs_tables(source):
    tables = {}

    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.is_dir():
            return None
        for txt_file in p.glob("*.txt"):
            try:
                tables[txt_file.name] = pd.read_csv(txt_file, dtype=str, keep_default_na=False)
            except Exception as e:
                st.error(f"Error reading {txt_file.name}: {e}")
        return tables

    with zipfile.ZipFile(source, "r") as z:
        for file_info in z.infolist():
            if file_info.filename.endswith(".txt") and not file_info.filename.startswith("__MACOSX"):
                clean_name = file_info.filename.split("/")[-1]
                if clean_name:
                    with z.open(file_info) as f:
                        tables[clean_name] = pd.read_csv(f, dtype=str, keep_default_na=False)
    return tables

def create_gtfs_zip(tables_dict):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for filename, df in tables_dict.items():
            csv_data = df.to_csv(index=False, encoding="utf-8")
            z.writestr(filename, csv_data)
    buffer.seek(0)
    return buffer

def reload_single_table(source_ref, filename):
    if isinstance(source_ref, (str, Path)):
        p = Path(source_ref)
        target = p / filename
        if not target.exists():
            matches = list(p.glob(f"**/{filename}"))
            if matches:
                target = matches[0]
            else:
                return pd.DataFrame()
        return pd.read_csv(target, dtype=str, keep_default_na=False)
    else:
        if hasattr(source_ref, "seek"):
            source_ref.seek(0)
        with zipfile.ZipFile(source_ref, "r") as z:
            for file_info in z.infolist():
                if not file_info.filename.startswith("__MACOSX"):
                    clean_name = file_info.filename.split("/")[-1]
                    if clean_name == filename:
                        with z.open(file_info) as f:
                            return pd.read_csv(f, dtype=str, keep_default_na=False)
        return pd.DataFrame()

def gtfs_time_to_seconds(time_str: str) -> int:
    if not time_str or not isinstance(time_str, str):
        return 0
    parts = time_str.strip().split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s
    except ValueError:
        return 0

def seconds_to_gtfs_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def shift_gtfs_time(time_str: str, delta_sec: int) -> str:
    return seconds_to_gtfs_time(gtfs_time_to_seconds(time_str) + delta_sec)

def shift_time_columns(df: pd.DataFrame, mask, columns: list[str], delta_sec: int) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df.loc[mask, col] = df.loc[mask, col].apply(lambda t: shift_gtfs_time(t, delta_sec))
    return df

def render_inline_cascader(prefix: str, tables: dict):
    stops_times_df = tables.get("stop_times.txt")
    trips_df = tables.get("trips.txt")
    stops_df = tables.get("stops.txt")

    if stops_times_df is None or trips_df is None:
        return

    with st.expander("Quick Cascade: Retime Downstream Stop Times", expanded=False):
        c_mode = st.radio(
            "Cascade Mode",
            ["Single Trip (Stop-to-Stop)", "Route Headways (Trip-To-Trip)"],
            horizontal=True,
            key=f"{prefix}_inline_cscade_mode"
        )

        filter_trips = None

        if c_mode.startswith("Single Trip"):
            col_t, col_s, col_m, col_btn = st.columns([2, 2, 1.5, 1.2], vertical_alignment="bottom")
            
            unique_trips = trips_df["trip_id"].dropna().unique().tolist()
            chosen_trip = col_t.selectbox("Trip ID", unique_trips, key=f"{prefix}_casc_trip")
            filter_trips = [chosen_trip]

            trip_stops = stops_times_df[stops_times_df["trip_id"] == chosen_trip].copy()
            if trip_stops.empty:
                st.warning(f"No stop times found for Trip `{chosen_trip}`.")
                return None

            trip_stops["stop_sequence"] = trip_stops["stop_sequence"].astype(int)
            trip_stops = trip_stops.sort_values("stop_sequence")

            if stops_df is not None and "stop_name" in stops_df.columns:
                trip_stops = trip_stops.merge(stops_df[["stop_id", "stop_name"]], on="stop_id", how="left")
            else:
                trip_stops["stop_name"] = trip_stops["stop_id"]

            seq_options = trip_stops["stop_sequence"].tolist()
            chosen_seq = col_s.selectbox(
                "Cascade from Stop",
                seq_options,
                format_func=lambda s: f"Seq {s}: {trip_stops[trip_stops['stop_sequence'] == s]['stop_name'].values[0]} ({trip_stops[trip_stops['stop_sequence'] == s]['departure_time'].values[0]})",
                key=f"{prefix}_casc_seq"
            )

            shift_min = col_m.number_input(
                "Shift (Minutes)",
                value=5.0,
                step=1.0,
                key=f"{prefix}_casc_shift_min"
            )

            if col_btn.button("Apply Cascade", key=f"{prefix}_casc_apply_btn", type="primary", width="stretch"):
                delta_sec = int(shift_min * 60)
                mask = (stops_times_df["trip_id"] == chosen_trip) & (stops_times_df["stop_sequence"].astype(int) >= chosen_seq)

                new_stop_times = stops_times_df.copy()
                shift_time_columns(new_stop_times, mask, ["arrival_time", "departure_time"], delta_sec)

                desc = f"Cascaded {shift_min:+}m on Trip {chosen_trip} (Seq {chosen_seq}+)"
                record_change(prefix, "stop_times.txt", desc, new_stop_times)
                
                st.success(f"Cascaded {shift_min:+} min starting from Seq {chosen_seq}!")
                st.rerun()
        else:
            col_r, col_t2, col_m2, col_btn2 = st.columns([2, 2, 1.5, 1.2], vertical_alignment="bottom")
            routes = sorted(trips_df["route_id"].dropna().unique().tolist())
            chosen_route = col_r.selectbox("Route", routes, key=f"{prefix}_casc_route")

            route_trips = trips_df[trips_df["route_id"] == chosen_route]["trip_id"].unique().tolist()
            filter_trips = route_trips

            matching_stops = stops_times_df[stops_times_df["trip_id"].isin(route_trips)]
            if matching_stops.empty:
                st.warning(f"No stop times found for Route `{chosen_route}`.")
                return None

            route_stops = stops_times_df[stops_times_df["trip_id"].isin(route_trips)].sort_values(
                ["trip_id", "stop_sequence"]
            ).groupby("trip_id").first().reset_index()
            route_stops["start_sec"] = route_stops["departure_time"].apply(gtfs_time_to_seconds)
            route_stops = route_stops.sort_values("start_sec").reset_index(drop=True)

            ordered_trips = route_stops["trip_id"].tolist()
            if not ordered_trips:
                st.warning("No trips found.")
                return

            target_trip = col_t2.selectbox(
                "Shift this Trip & subsequent",
                ordered_trips,
                format_func=lambda tid: f"{tid} (Departs {route_stops[route_stops['trip_id'] == tid]['departure_time'].values[0]})",
                key = f"{prefix}_casc_target_trip"
            )

            shift_min_hw = col_m2.number_input(
                "Shift (Minutes)",
                value=5.0,
                step=1.0,
                key=f"{prefix}_casc_shift_hw"
            )

            if col_btn2.button("Apply Cascade", key=f"{prefix}_casc_apply_hw_btn", type="primary", width="stretch"):
                delta_sec = int(shift_min_hw * 60)
                start_idx = ordered_trips.index(target_trip)
                trips_to_shift = ordered_trips[start_idx:]
                
                mask = stops_times_df["trip_id"].isin(trips_to_shift)

                new_stop_times = stops_times_df.copy()
                shift_time_columns(new_stop_times, mask, ["arrival_time", "departure_time"], delta_sec)

                desc = f"Shifted {len(trips_to_shift)} trips on Route {chosen_route} by {shift_min_hw:+}m"
                record_change(prefix, "stop_times.txt", desc, new_stop_times)

                st.success(f"Shifted {len(trips_to_shift)} trips by {shift_min_hw:+} min!")
                st.rerun()

        enable_filter = st.checkbox(
            "Filter table below to selected trip(s)",
            value=True,
            key=f"{prefix}_toggle_filter_below"
        )
        return filter_trips if enable_filter else None
    
def render_inline_frequencies_cascader(prefix: str, tables: dict):
    freq_df = tables.get("frequencies.txt")
    if freq_df is None or freq_df.empty:
        st.info("`frequencies.txt` is either empty or not included in this feed.")
        return

    with st.expander("Quick Cascade: Retime Frequency Windows", expanded=False):
        unique_trips = freq_df["trip_id"].dropna().unique().tolist()
        if not unique_trips:
            return

        col_t, col_action = st.columns([2, 3], vertical_alignment="bottom")
        chosen_trip = col_t.selectbox("Template Trip ID", unique_trips, key=f"{prefix}_freq_trip")
        action_mode = col_action.radio(
            "Action",
            ["Extend/Shorten Window (Boundry Cascade)", "Shift Entire Trip Schedule"],
            horizontal=True,
            key=f"{prefix}_freq_action_mode"
        )

        trip_bands = freq_df[freq_df["trip_id"] == chosen_trip].copy()
        trip_bands["start_sec"] = trip_bands["start_time"].apply(gtfs_time_to_seconds)
        trip_bands = trip_bands.sort_values("start_sec").reset_index(drop=True)
        trip_bands["headway_min"] = pd.to_numeric(trip_bands["headway_secs"], errors="coerce") / 60.0

        st.caption(f"Found  {len(trip_bands)} frequency window(s) for Trip `{chosen_trip}`:")

        if action_mode.startswith("Extend"):
            col_b, col_shift, col_btn = st.columns([3, 2, 1.5], vertical_alignment="bottom")
            chosen_band_idx = col_b.selectbox(
                "Select Window to Adjust End Time",
                range(len(trip_bands)),
                format_func = lambda i: f"Band {i+1}: {trip_bands.loc[i, 'start_time']} = {trip_bands.loc[i, 'end_time']} (Every {trip_bands.loc[i, 'headway_min']:.0f}m)",
                key=f"{prefix}_freq_band_idx"
            )

            shift_min = col_shift.number_input("Adjust End Time (+/- Minutes)", value=30.0, step=5.0, key=f"{prefix}_freq_band_shift")
            affected = len(trip_bands) - 1 - chosen_band_idx
            st.info(f"Adjusting Band {chosen_band_idx + 1}'s end time by **{shift_min:+} min** cascades to **{affected} downstream window(s)**.")

            if col_btn.button("Apply Windows Cascade", key=f"{prefix}_btn_apply_freq_band", type="primary", width="stretch"):
                delta_sec = int(shift_min * 60)
                new_freq_df = freq_df.copy()

                target_start = trip_bands.loc[chosen_band_idx, "start_time"]
                mask_target = (new_freq_df["trip_id"] == chosen_trip) & (new_freq_df["start_time"] == target_start)
                shift_time_columns(new_freq_df, mask_target, ["end_time"], delta_sec)

                if affected > 0:
                    downstream_starts = trip_bands.loc[chosen_band_idx + 1:, "start_time"].tolist()
                    mask_downstream = (new_freq_df["trip_id"] == chosen_trip) & (new_freq_df["start_time"].isin(downstream_starts))
                    shift_time_columns(new_freq_df, mask_downstream, ["start_time", "end_time"], delta_sec)

                record_change(prefix, "frequencies.txt", f"Cascaded Band {chosen_band_idx + 1} ({shift_min:+}m) on Trip {chosen_trip}", new_freq_df)
                st.rerun()
        else:
            col_s2, col_btn2 = st.columns([3, 1.5], vertical_alignment="bottom")
            shift_all_min = col_s2.number_input("Shift All Windows (+/- Minutes)", value=15.0, step=5.0, key=f"{prefix}_freq_shift_all")

            if col_btn2.button("Shift All Windows", key=f"{prefix}_btn_apply_freq_all", type="primary", width="stretch"):
                delta_sec = int(shift_all_min * 60)
                new_freq_df = freq_df.copy()

                mask_trip = new_freq_df["trip_id"] == chosen_trip
                shift_time_columns(new_freq_df, mask_trip, ["start_time", "end_time"], delta_sec)

                record_change(prefix, "frequencies.txt", f"Shifted all windows on Trip {chosen_trip} by {shift_all_min:+}m", new_freq_df)
                st.success(f"Shifted all windows for Trip `{chosen_trip}` by {shift_all_min:+} min!")
                st.rerun()
                    