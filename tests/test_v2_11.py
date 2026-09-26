"""v2.11.0: packet back photo (front/back sides), logo placeholders."""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="garden-v211-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))
os.environ.setdefault("GARDEN_DATABASE_URL", f"sqlite:///{TMP / 'garden.db'}")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import UPLOAD_DIR, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)

# Valid PNG magic bytes + padding; save_upload sniffs the header only.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128


def _packet():
    r = client.post("/api/seed-packets/", json={"variety_name": "Fatalii", "vendor_name": "Baker Creek"})
    assert r.status_code == 201, r.text
    return r.json()


def _upload(pid, side=None):
    files = {"file": ("packet.png", io.BytesIO(PNG), "image/png")}
    url = f"/api/seed-packets/{pid}/photo"
    if side:
        url += f"?side={side}"
    return client.post(url, files=files)


def _disk_path(url_path: str) -> Path:
    assert url_path.startswith("/uploads/")
    return UPLOAD_DIR / url_path[len("/uploads/"):]


def test_front_and_back_photos():
    p = _packet()

    # Default side is front; back stays empty.
    r = _upload(p["id"])
    assert r.status_code == 200, r.text
    front = r.json()["photo_path"]
    assert front and r.json()["photo_back_path"] == ""

    # Back photo goes to photo_back_path.
    r = _upload(p["id"], side="back")
    assert r.status_code == 200, r.text
    back = r.json()["photo_back_path"]
    assert back and back != front
    assert _disk_path(front).exists() and _disk_path(back).exists()

    # Re-uploading the front keeps the back intact.
    r = _upload(p["id"])
    assert r.status_code == 200, r.text
    assert r.json()["photo_back_path"] == back
    assert not _disk_path(front).exists()  # old front file replaced

    # Unknown side rejected.
    r = _upload(p["id"], side="sideways")
    assert r.status_code == 422

    # Deleting the packet removes both files from disk.
    r = client.delete(f"/api/seed-packets/{p['id']}")
    assert r.status_code == 204, r.text
    assert not _disk_path(back).exists()
    remaining = [f for f in (UPLOAD_DIR / "seed-packets" / str(p["id"])).rglob("*") if f.is_file()]
    assert remaining == []


def test_logo_placeholders_served():
    # Placeholder SVG is served from static.
    r = client.get("/static/img/logo-placeholder.svg")
    assert r.status_code == 200, r.text
    assert "LOGO" in r.text

    # Every page (via base.html) references it: nav, footer, favicon.
    r = client.get("/seeds")
    assert r.status_code == 200, r.text
    assert r.text.count("/static/img/logo-placeholder.svg") >= 3
