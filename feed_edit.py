import os
import socket
import sys
import traceback
import webbrowser
from streamlit.web import cli as stcli

def find_free_port(prefered_port=8501):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", prefered_port))
            return prefered_port
        except OSError:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind(("", 0))
                return s2.getsockname()[1]

if __name__ == "__main__":
    try:
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
            "--server.port={port}",
            "--browser.serverAddress=localhost",
        ]

        sys.exit(stcli.main())

    except SystemExit:
        pass
    except Exception as e:
        print("\n" + "=" * 60)
        print("AN ERROR OCCURRED WHILE LAUNCHING GTFS FEED EDITOR:")
        traceback.print_exc()
        print("=" * 60)
        input("\nPress Enter to exit...")