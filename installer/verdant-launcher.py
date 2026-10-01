"""Verdant Windows launcher (PyInstaller entry point).

Sets per-user data locations under %LOCALAPPDATA%\\Verdant, starts the
FastAPI server on 127.0.0.1, and opens the garden journal in the browser.

The env vars must be set BEFORE importing app.main: app/database.py reads
them at import time.
"""
from __future__ import annotations

import os
import threading
import webbrowser


def main() -> None:
    local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    base = os.path.join(local_app_data, "Verdant")
    os.environ.setdefault("GARDEN_DATA_DIR", os.path.join(base, "data"))
    os.environ.setdefault("GARDEN_UPLOAD_DIR", os.path.join(base, "uploads"))
    os.makedirs(os.environ["GARDEN_DATA_DIR"], exist_ok=True)
    os.makedirs(os.environ["GARDEN_UPLOAD_DIR"], exist_ok=True)

    port = int(os.environ.get("GARDEN_PORT", "3113"))
    url = f"http://127.0.0.1:{port}"

    print(f"Verdant is starting at {url} ...")
    print("Keep this window open while you use Verdant.")
    print("Close the window to stop the server.")
    threading.Timer(2.0, lambda: webbrowser.open(url)).start()

    import app.main  # noqa: E402  (after the env vars above are set)
    import uvicorn

    uvicorn.run(app.main.app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
