import io
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import streamlit as st

def pick_folder():
    try:
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
        file_path = Path(source_ref) / filename
        return pd.read_csv(file_path, dtype=str, keep_default_na=False)
    else:
        with zipfile.ZipFile(source_ref, "r") as z:
            with z.open(filename) as f:
                return pd.read_csv(f, dtype=str, keep_default_na=False)