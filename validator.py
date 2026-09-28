import os
import json
import tempfile
import subprocess
import urllib.request
from pathlib import Path
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

VALIDATOR_VERSION = "8.0.1"
VALIDATOR_URL = f"https://github.com/MobilityData/gtfs-validator/releases/download/v{VALIDATOR_VERSION}/gtfs-validator-{VALIDATOR_VERSION}-cli.jar"

def ensure_validator_jar(jar_path=None):
    if jar_path is None:
        jar_path = f"gtfs_validator-{VALIDATOR_VERSION}-cli.jar"

    p = Path(jar_path)
    if not p.is_file():
        with st.spinner(
            f"Downloading MobilityData GTFS Validator v{VALIDATOR_VERSION}..."
        ):
            try:
                urllib.request.urlretrieve(VALIDATOR_URL, str(p))
                st.success("Validator JAR downloaded and ready.")
            except Exception as e:
                return(
                    None,
                    f"Failed to download validator JAR from {VALIDATOR_URL}"
                    f" {e}"
                )
    return str(p.resolve()), None

def run_gtfs_validator(jar_path, tables_dict, create_gtfs_zip_fn):
    resolved_jar, err = ensure_validator_jar(jar_path)
    if err:
        return False, None, None, err

    with tempfile.TemporaryDirectory() as tmpdir:
        input_zip_path = os.path.join(tmpdir, "gtfs_feed.zip")
        output_dir = os.path.join(tmpdir, "output")
        os.makedirs(output_dir, exist_ok=True)

        zip_buffer = create_gtfs_zip_fn(tables_dict)
        with open(input_zip_path, "wb") as f:
            f.write(zip_buffer.getvalue())

        cmd = [
            "java",
            "-jar",
            resolved_jar,
            "-i",
            input_zip_path,
            "-o",
            output_dir,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False
            )
        except Exception as e:
            return False, None, None, f"Error executing Java CLI: {e}"

        report_json_path = os.path.join(output_dir, "report.json")
        report_html_path = os.path.join(output_dir, "report.html")

        report_json = None
        html_content = None

        if os.path.exists(report_json_path):
            with open(report_json_path, "r", encoding="utf-8", errors="replace") as f:
                try:
                    report_json = json.load(f)
                except Exception:
                    pass
        if os.path.exists(report_html_path):
            with open(report_html_path, "r", encoding="utf-8", errors="replace") as f:
                html_content = f.read()

        combined_logs = f"=== STDOUT ===\n{result.stdout}\n\n=== STDERR ===\n{result.stderr}"
        return True, report_json, html_content, combined_logs

def render_validator_ui(jar_path, tables_dict, create_gtfs_zip_fn, key_prefix="default"):
    st.subheader("MobilityData GTFS Validator")

    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    with c1:
        jar_location = st.text_input(
            "Validator JAR Path",
            value=jar_path,
            placeholder="e.g. gtfs-validator-8.0.1-cli.jar",
            key=f"{key_prefix}_validator_jar_path"
        )
    with c2:
        run_btn = st.button("Run Validation", type="primary", width='stretch', key=f"{key_prefix}_run_btn")

    if run_btn:
        with st.spinner("Running MobilityData GTFS Validator"):
            success, report_json, html_content, logs = run_gtfs_validator(
                jar_location, tables_dict, create_gtfs_zip_fn
            )

            st.session_state[f"{key_prefix}_validation_executed"] = True
            st.session_state[f"{key_prefix}_validation_success"] = success
            st.session_state[f"{key_prefix}_validation_json"] = report_json
            st.session_state[f"{key_prefix}_validation_html"] = html_content
            st.session_state[f"{key_prefix}_validation_logs"] = logs

    if st.session_state.get(f"{key_prefix}_validation_executed"):
        if not st.session_state.get(f"{key_prefix}_validation_success"):
            st.error(st.session_state.get(f"{key_prefix}_validation_logs"))
            return

        report_json = st.session_state.get(f"{key_prefix}_validation_json")
        html_content = st.session_state.get(f"{key_prefix}_validation_html")

        if report_json:
            notices = report_json.get("notices", [])
            errors = [n for n in notices if n.get("severity") == "ERROR"]
            warnings = [n for n in notices if n.get("severity") == "WARNING"]
            infos = [n for n in notices if n.get("severity") == "INFO"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Notices", len(notices))
        m2.metric("Errors 🔴", len(errors))
        m3.metric("Warnings 🟡", len(warnings))
        m4.metric("Info 🔵", len(infos))

        with st.expander("Breakdown by Code", expanded=False):
            summary_data = []
            for n in notices:
                summary_data.append({
                    "Code": n.get("code"),
                    "Severity": n.get("severity"),
                    "Count": n.get("totalNotices", 1),
                })
            if summary_data:
                df_notices = pd.DataFrame(summary_data).drop_duplicates()
                st.dataframe(df_notices, width='stretch', hide_index=True)

        if html_content:
            st.markdown("### Interactive HTML Report")
            components.html(html_content, height=850, scrolling=True)
        else:
            st.info("HTML report was not generated. Check logs below.")

        with st.expander("View Console Output / Logs"):
            st.code(st.session_state.get(f"{key_prefix}_validation_logs", ""), language="text")