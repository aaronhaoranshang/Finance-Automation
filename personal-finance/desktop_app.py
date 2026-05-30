from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

from streamlit.web import bootstrap


def bundled_path(relative_path: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / relative_path


def main() -> None:
    app_path = bundled_path("src/app.py")
    port = int(os.environ.get("PERSONAL_FINANCE_PORT", "8501"))
    url = f"http://localhost:{port}"

    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    bootstrap.run(
        str(app_path),
        False,
        [],
        flag_options={
            "server.address": "localhost",
            "server.port": port,
            "server.headless": True,
            "browser.gatherUsageStats": False,
        },
    )


if __name__ == "__main__":
    main()
