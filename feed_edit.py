import os
import sys
import webbrowser
from streamlit.web import cli as stcli

if __name__ == "__main__":

    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    script_path = os.path.join(base_dir, "gtfs.py")

    sys.argv = [
        "streamlit",
        "run",
        script_path,
        "--global.developmentMode=false",
        "--server.headless=false",
        "--server.port=8501",
        "--browser.serverAddress=localhost",
    ]

    webbrowser.open("http://localhost:8501")

    sys.exit(stcli.main())