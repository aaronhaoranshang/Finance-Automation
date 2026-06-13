from __future__ import annotations

import os
import sys
from pathlib import Path

from streamlit.web import cli as streamlit_cli


def bundled_path(relative_path: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / relative_path


def main() -> None:
    app_path = bundled_path("src/app.py")
    backend_port = int(os.environ.get("PERSONAL_FINANCE_PORT", "8501"))
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--global.developmentMode",
        "false",
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(backend_port),
        "--server.headless",
        "false",
        "--browser.gatherUsageStats",
        "false",
    ]
    streamlit_cli.main()


if __name__ == "__main__":
    main()
