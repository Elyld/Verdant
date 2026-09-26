"""Backup & restore tests: export zip contents, full round-trip restore.

Run with:  pytest -q      (shares the same temp DB as test_api.py)
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="backup-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def make_plant(client, name):
    res = client.post("/api/plants/", json={"variety_name": name, "species_type": "Tomato"})
    assert res.status_code == 201, res.text
    return res.json()


def seed(client):
    """Create a plant + harvest + observation with an uploaded image."""
    plant = make_plant(client, "Backup Tomato")
    res = client.post("/api/harvests/", json={
        "plant_id": plant["id"], "date": "2026-09-01",
        "quantity": 4, "unit": "fruit", "weight": 12.5,
    })
    assert res.status_code == 201, res.text
    res = client.post("/api/observations/", json={
        "plant_id": plant["id"], "date": "2026-09-02",
        "plant_name": "Backup Tomato", "health_scale": 8, "notes": "backup test",
    })
    assert res.status_code == 201, res.text
    obs = res.json()
    res = client.post(
        f"/api/observations/{obs['id']}/images",
        files={"files": ("leaf.jpg", b"\xff\xd8\xff" + b"fake-jpeg-bytes", "image/jpeg")},
    )
    assert res.status_code in (200, 201), res.text
    return plant


def download_backup(client):
    res = client.get("/api/backup/export")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    assert "verdant-backup-" in res.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(res.content))


def test_export_contains_data_and_files(client):
    seed(client)
    zf = download_backup(client)
    assert "data.json" in zf.namelist()
    manifest = json.loads(zf.read("data.json"))
    assert manifest["format"] == "verdant-backup"
    tables = manifest["tables"]
    assert any(p["variety_name"] == "Backup Tomato" for p in tables["plants"])
    assert any(h["quantity"] == 4 for h in tables["harvests"])
    assert len(tables["observation_images"]) >= 1
    # the uploaded image bytes are bundled under files/
    img_names = [n for n in zf.namelist() if n.startswith("files/") and n.endswith(".jpg")]
    assert img_names, zf.namelist()
    assert zf.read(img_names[0]) == b"\xff\xd8\xff" + b"fake-jpeg-bytes"


def test_round_trip_restore(client):
    seed(client)
    res = client.get("/api/backup/export")
    assert res.status_code == 200
    backup_bytes = res.content
    extra = make_plant(client, "Should Disappear")
    res = client.post(
        "/api/backup/import",
        files={"file": ("verdant-backup-test.zip", backup_bytes, "application/zip")},
    )
    assert res.status_code == 200, res.text
    counts = res.json()["restored"]
    assert counts["plants"] >= 1
    plants = client.get("/api/plants/").json()
    names = [p["variety_name"] for p in plants]
    assert "Backup Tomato" in names
    assert "Should Disappear" not in names
    # harvest survived with its data
    harvests = client.get("/api/harvests/").json()
    assert any(h["quantity"] == 4 and h["weight"] == 12.5 for h in harvests)
    # image row + file bytes survived the restore
    assert counts["observation_images"] >= 1
    from app.database import UPLOAD_DIR as _UD

    jpgs = list(_UD.rglob("*.jpg"))
    assert jpgs, "no uploaded images on disk after restore"
    assert any(p.stat().st_size > 0 for p in jpgs)


def test_import_rejects_garbage(client):
    res = client.post(
        "/api/backup/import",
        files={"file": ("nope.zip", b"definitely not a zip", "application/zip")},
    )
    assert res.status_code == 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps({"format": "something-else"}))
    res = client.post(
        "/api/backup/import",
        files={"file": ("wrong.zip", buf.getvalue(), "application/zip")},
    )
    assert res.status_code == 400


def test_backup_page_renders(client):
    res = client.get("/backup")
    assert res.status_code == 200
    assert "Backup &amp; restore" in res.text or "Backup & restore" in res.text


def test_export_without_photos(client):
    seed(client)
    res = client.get("/api/backup/export?include_photos=false")
    assert res.status_code == 200, res.text
    assert "-nophotos-" in res.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    manifest = json.loads(zf.read("data.json"))
    assert manifest["includes_photos"] is False
    assert manifest["tables"]["plants"], "data rows still exported"
    assert not [n for n in zf.namelist() if n.startswith("files/")], zf.namelist()


def test_export_default_still_includes_photos(client):
    zf = download_backup(client)
    manifest = json.loads(zf.read("data.json"))
    assert manifest["includes_photos"] is True
    assert [n for n in zf.namelist() if n.startswith("files/")]


def test_restore_without_photos_keeps_uploads(client):
    seed(client)
    res = client.get("/api/backup/export?include_photos=false")
    assert res.status_code == 200
    backup_bytes = res.content
    from app.database import UPLOAD_DIR as _UD

    before = {p.name for p in _UD.rglob("*") if p.is_file()}
    assert before, "expected an uploaded file before restore"
    res = client.post(
        "/api/backup/import",
        files={"file": ("verdant-backup-nophotos.zip", backup_bytes, "application/zip")},
    )
    assert res.status_code == 200, res.text
    assert res.json()["photos_included"] is False
    after = {p.name for p in _UD.rglob("*") if p.is_file()}
    assert before <= after, "photo-less restore must not wipe current uploads"
