import json
import os
import pandas as pd
import streamlit as st
import pydeck as pdk
from pathlib import Path

def parse_hex_color(hex_str, default_color):
    if not isinstance(hex_str, str):
        return default_color
    s = hex_str.strip().lstrip("#")
    if len(s) == 6:
        try:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            alpha = default_color[3] if len(default_color) > 3 else 220
            return [r, g, b, alpha]
        except ValueError:
            return default_color
    return default_color

def process_feed_spatial(tables_dict, feed_label, line_color, stop_color, selected_shape=None, use_route_colors=True,):
    layers = []
    lats=[]
    lons=[]

    shape_to_color = {}
    shape_to_name = {}

    if "trips.txt" in tables_dict and "routes.txt" in tables_dict:
        tr = tables_dict["trips.txt"]
        ro = tables_dict["routes.txt"]

        if ("shape_id" in tr.columns and "route_id" in tr.columns and "route_id" in ro.columns):
            tr_clean = (
                tr[["shape_id", "route_id"]]
                .dropna()
                .drop_duplicates(subset=["shape_id"])
            )
            merged = tr_clean.merge(ro, on='route_id', how="left")

            for _, row in merged.iterrows():
                shp = str(row["shape_id"])
                if use_route_colors and "route_color" in row:
                    shape_to_color[shp] = parse_hex_color(
                        row.get("route_color", ""), line_color
                    )
                else:
                    shape_to_color[shp] = line_color

                s_name = str(row.get("route_short_name", "")).strip()
                l_name = str(row.get("route_long_name", "")).strip()
                route_label = (
                    s_name
                    if s_name
                    else (l_name if l_name else str(row.get("route_id")))
                )
                shape_to_name[shp] = route_label

    if "shapes.txt" in tables_dict:
        df_shapes = tables_dict["shapes.txt"].copy()
        req_s = {"shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"}
        if req_s.issubset(df_shapes.columns) and not df_shapes.empty:
            df_shapes["shape_pt_lat"] = pd.to_numeric(df_shapes["shape_pt_lat"], errors="coerce")
            df_shapes["shape_pt_lon"] = pd.to_numeric(df_shapes["shape_pt_lon"], errors="coerce")
            df_shapes["shape_pt_sequence"] = pd.to_numeric(df_shapes["shape_pt_sequence"], errors="coerce")
            df_shapes = df_shapes.dropna(subset=["shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"])

            if selected_shape and selected_shape != "All Shapes":
                df_shapes = df_shapes[df_shapes["shape_id"] == selected_shape]

            if not df_shapes.empty:
                df_shapes = df_shapes.sort_values(by=["shape_id", "shape_pt_sequence"])
                path_data = (
                    df_shapes.groupby("shape_id")
                    .apply(lambda g: g[["shape_pt_lon", "shape_pt_lat"]].values.tolist(), include_groups=False)
                    .reset_index(name="path")
                )
                path_data["feed"] = feed_label
                path_data["shape_id_str"] = path_data["shape_id"].astype(str)

                path_data["color"] = path_data["shape_id_str"].apply(
                    lambda sid: shape_to_color.get(sid, line_color)
                )
                path_data["route_name"] = path_data["shape_id_str"].apply(
                    lambda sid: shape_to_name.get(sid, "N/A")
                )
                path_data["tooltip_text"] = (
                    f"Feed: {feed_label}\nRoute: "
                    + path_data["route_name"]
                    + "\nShape: "
                    + path_data["shape_id_str"]
                )

                layers.append(
                    pdk.Layer(
                        "PathLayer",
                        id=f"{feed_label}_paths",
                        data=path_data,
                        get_path="path",
                        get_color="color",
                        width_scale=1,
                        width_min_pixels=3,
                        pickable=True
                    )
                )
                lats.extend(df_shapes["shape_pt_lat"].tolist())
                lons.extend(df_shapes["shape_pt_lon"].tolist())

    if "stops.txt" in tables_dict:
        df_stops = tables_dict["stops.txt"].copy()
        if {"stop_lat", "stop_lon", "stop_id"}.issubset(df_stops.columns) and not df_stops.empty:
            df_stops["stop_lat"] = pd.to_numeric(df_stops["stop_lat"], errors="coerce")
            df_stops["stop_lon"] = pd.to_numeric(df_stops["stop_lon"], errors="coerce")
            df_stops = df_stops.dropna(subset=["stop_lat", "stop_lon"])

            if selected_shape and selected_shape != "All Shapes":
                if "trips.txt" in tables_dict and "stop_times.txt" in tables_dict:
                    tr = tables_dict["trips.txt"]
                    st_df = tables_dict["stop_times.txt"]
                    if "shape_id" in tr.columns and "trip_id" in tr.columns and "trip_id" in st_df.columns:
                        m_trips = tr[tr["shape_id"] == selected_shape]["trip_id"].unique()
                        m_stops = st_df[st_df["trip_id"].isin(m_trips)]["stop_id"].unique()
                        if len(m_stops) > 0:
                            df_stops = df_stops[df_stops["stop_id"].isin(m_stops)]
            
            if not df_stops.empty:
                df_stops["feed"] = feed_label
                df_stops["tooltip_next"] = (
                    f"Feed: {feed_label}\nStop: "
                    + df_stops.get("stop_name", df_stops["stop_id"]).astype(
                        str
                    )
                    + "\nID: "
                    + df_stops["stop_id"].astype(str)
                )
                
                layers.append(
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=df_stops,
                        get_position=["stop_lon", "stop_lat"],
                        get_radius=20,
                        radius_min_pixels=4,
                        radius_max_pixels=8,
                        get_fill_color=stop_color,
                        pickable=True
                    )
                )
                lats.extend(df_stops["stop_lat"].tolist())
                lons.extend(df_stops["stop_lon"].tolist())

    return layers, lats, lons

def render_dual_gtfs_map(tables_a, tables_b, height=800):
    st.subheader("Network Map View")
    has_a = bool(tables_a)
    has_b = bool(tables_b)

    # if not has_a and not has_b:
    #     st.info("Load Feed A or Feed B below to view map routes and stops.")
    #     return

    mode_options = []
    if has_a:
        mode_options.append("Feed A")
    if has_b:
        mode_options.append("Feed B")
    if has_a and has_b:
        mode_options.append("Overlay Both")

    m_col1, m_col2 = st.columns([2, 2], vertical_alignment="center")

    with m_col1:
        if mode_options:
            map_mode = st.radio(
                "Map Display Mode:",
                mode_options,
                horizontal=True,
                key="dual_map_mode"
            )
        else:
            map_mode = None
            st.caption("System Reference. Upload GTFS feed to overlay routes and stops.")

    selected_shape_a = None
    selected_shape_b = None
    overlay_top = "Feed A"

    with m_col2:
        c_rail, c_color = st.columns([1.2, 1], vertical_alignment="center")
        with c_rail:
            show_rail_ref = st.checkbox(
                "Metro System Refrence",
                value=True,
                help="Overlays LA Metro Rail and BRT Network"
            )
        # with c_color:
        #     use_route_colors = st.checkbox(
        #         "Use route_color",
        #         value=True,
        #         help="Color routes by their GTFS route_color."
        #     )
        if map_mode == "Feed A" and "shapes.txt" in tables_a:
            sh_a = sorted(tables_a["shapes.txt"]["shape_id"].unique()) if "shape_id" in tables_a["shapes.txt"].columns else []
            selected_shape_a = st.selectbox("Filter Shape:", ["All Shapes"] + sh_a, key="sh_filter_a")
        elif map_mode == "Feed B" and "shapes.txt" in tables_b:
            sh_b = sorted(tables_b["shapes.txt"]["shape_id"].unique()) if "shape_id" in tables_b["shapes.txt"].columns else []
            selected_shape_b = st.selectbox("Filter Shape:", ["All Shapes"] + sh_b, key="sh_filter_b")
        elif map_mode == "Overlay Both":
            overlay_top = st.radio(
                "Render on Top:",
                ["Feed A", "Feed B"],
                horizontal=True,
                key="overlay_layer_top",
                help="Choose which feed's routes and stops appear above the other.",
            )
        else:
            overlay_top = "Feed A"

    layers_a, layers_b = [], []
    all_lats, all_lons = [], []

    if map_mode in ["Feed A", "Overlay Both"] and has_a:
        layers_a, lat_a, lon_a = process_feed_spatial(
            tables_a, "Feed A", [0, 114, 206, 220], [0, 114, 206, 240], selected_shape_a,
        )
        all_lats.extend(lat_a)
        all_lons.extend(lon_a)

    if map_mode in ["Feed B", "Overlay Both"] and has_b:
        layers_b, lat_b, lon_b = process_feed_spatial(
            tables_b, "Feed B", [235, 110, 30, 220], [235, 110, 30, 240], selected_shape_b,
        )
        all_lats.extend(lat_b)
        all_lons.extend(lon_b)

    if map_mode == "Overlay Both":
        if overlay_top == "Feed A":
            all_layers = (
                layers_b + layers_a
            )  # Feed B on bottom, Feed A on top
        else:
            all_layers = (
                layers_a + layers_b
            )  # Feed A on bottom, Feed B on top
    else:
        all_layers = layers_a + layers_b

    rail_layers = []
    if show_rail_ref:
        rail_file = Path("LA_Metro_System.geojson")
        if rail_file.is_file():
            try:
                with open(rail_file, "r", encoding="utf-8") as f:
                    geojson_data = json.load(f)

                for feat in geojson_data.get("features", []):
                    props = feat.get("properties", {})
                    hex_col = props.get("route_color", "")
                    props["line_color"] = parse_hex_color(
                        hex_col, [100, 100, 100, 220]
                    )

                    line_name = (
                        props.get("route_long_name")
                        or props.get("route_desc")
                        or "Metro Rail"
                    )
                    props["tooltip_next"] = f"{line_name}"

                rail_layers.append(
                    pdk.Layer(
                        "GeoJsonLayer",
                        id="la_metro_rail_ref",
                        data=geojson_data,
                        stroked=True,
                        filled=False,
                        opacity=0.05,
                        line_width_scale=1,
                        line_width_min_pixels=3,
                        get_line_color="properties.line_color",
                        get_line_width=3,
                    )
                )
            except Exception as e:
                st.caption(f"Could not load Metro Rail Layer: {e}")

    all_layers = rail_layers + all_layers

    if not all_layers:
        st.warning("No map layers available to display.")
        return

    if all_lats:
        center_lat = float(sum(all_lats) / len(all_lats))
        center_lon = float(sum(all_lons) / len(all_lons))
        zoom_level = 10
    else:
        center_lat = 34.0522
        center_lon = -118.2437
        zoom_level = 10

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom_level,
        pitch=0,
    )

    deck_key = f"map_deck_{map_mode}_{selected_shape_a}_{selected_shape_b}_{len(all_layers)}"

    st.pydeck_chart(
        pdk.Deck(
            layers=all_layers,
            initial_view_state=view_state,
            tooltip={"text": "Feed: {feed}\nName: {stop_name}\nID: {stop_id}"},
            map_style="light",
        ),
        height=height,
        key=deck_key,
    )