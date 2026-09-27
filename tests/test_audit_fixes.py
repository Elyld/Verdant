"""Regression tests for the pre-release audit fixes (chore/release-audit).

Run with:  pytest -q
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from datetime import date
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="audit-fix-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import UPLOAD_DIR, init_db  # noqa: E402
from app.frost import annualize  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def test_watering_log_delete_route():
    """DELETE /api/watering-logs/{id} used to 422: the path said
    {watering_id} but the handler took log_id."""
    r = client.post("/api/locations/", params={"name": "Audit Bed", "type": "Raised Bed"})
    assert r.status_code == 201, r.text
    loc_id = r.json()["id"]
    r = client.post("/api/watering-logs/", json={
        "location_id": loc_id, "date": "2026-09-20", "method": "hose",
    })
    assert r.status_code == 201, r.text
    log_id = r.json()["id"]
    r = client.delete(f"/api/watering-logs/{log_id}")
    assert r.status_code == 204, r.text
    assert client.get(f"/api/watering-logs/{log_id}").status_code == 404


def test_annualize_feb29_no_crash():
    """A Feb 29 exact frost date must not 500 in non-leap years."""
    assert annualize(2, 29, today=date(2026, 1, 15)) == date(2026, 2, 28)
    # Non-leap year with no Feb 29: clamps to Feb 28 rather than crashing.
    assert annualize(2, 29, today=date(2025, 6, 1)) == date(2026, 2, 28)
    assert annualize(2, 29, today=date(2024, 1, 15)) == date(2024, 2, 29)


def test_album_whitespace_name_rejected():
    r = client.post("/api/albums/", data={"name": "   "})
    assert r.status_code in (400, 422), r.text


def test_seed_source_patch_bad_date_422():
    r = client.post("/api/seed-sources/", json={
        "source_id": "SRC-AUDIT-1", "source": "Audit Seeds",
        "variety": "Audit Tomato", "acquired_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    src_id = r.json()["id"]
    r = client.patch(f"/api/seed-sources/{src_id}", json={"acquired_date": "not-a-date"})
    assert r.status_code == 422, r.text
    # A good date still works.
    r = client.patch(f"/api/seed-sources/{src_id}", json={"acquired_date": "2026-02-02"})
    assert r.status_code == 200, r.text


def test_seed_source_public_id_protected():
    r = client.post("/api/seed-sources/", json={
        "source_id": "SRC-AUDIT-2", "source": "Audit Seeds", "variety": "Audit Pepper",
    })
    assert r.status_code == 201, r.text
    src_id, public = r.json()["id"], r.json()["source_id"]
    r = client.patch(f"/api/seed-sources/{src_id}", json={"source_id": "SRC-HACKED"})
    assert r.status_code == 200, r.text
    assert r.json()["source_id"] == public


def test_patch_ignores_relationship_names():
    """Raw-dict PATCH with a relationship attr (e.g. 'plant') used to 500
    at commit; now it is ignored."""
    r = client.post("/api/plants/", json={"variety_name": "Audit Plant", "species_type": "Test"})
    assert r.status_code == 201, r.text
    plant_id = r.json()["id"]
    r = client.post("/api/harvests/", json={
        "plant_id": plant_id, "date": "2026-09-20", "quantity": 3,
    })
    assert r.status_code == 201, r.text
    h_id, public = r.json()["id"], r.json()["harvest_id"]
    r = client.patch(f"/api/harvests/{h_id}", json={"plant": plant_id, "bogus_key": 1})
    assert r.status_code == 200, r.text
    # Public ID is not rewritable and quantity validation runs on PATCH.
    r = client.patch(f"/api/harvests/{h_id}", json={"harvest_id": "H-HACKED"})
    assert r.status_code == 200, r.text
    assert r.json()["harvest_id"] == public
    r = client.patch(f"/api/harvests/{h_id}", json={"quantity": 0})
    assert r.status_code == 422, r.text
    r = client.patch(f"/api/harvests/{h_id}", json={"quantity": "lots"})
    assert r.status_code == 422, r.text


def test_import_csv_duplicate_ids_in_file_422():
    """Two rows with the same ID in one file used to die at commit with a
    500 and zero rows imported; now it is a clear 422."""
    csv_text = (
        "Location ID,Name,Type,Light\n"
        "LOC-DUP,Audit Dup A,Container,Full Sun\n"
        "LOC-DUP,Audit Dup B,Container,Full Sun\n"
    )
    r = client.post(
        "/api/import/run",
        data={"entity": "locations"},
        files={"file": ("dup.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert r.status_code == 422, r.text
    assert "duplicate" in r.json()["detail"].lower()


def test_weather_celsius_keys():
    """Celsius payloads must use _c keys (the old _f keys holding °C values
    were a trap for every future consumer)."""
    from app.routers.weather import _convert
    fc = {
        "current": {"temp_f": 77.0},
        "hourly": [{"temp_f": 77.0}],
        "daily": [{"tmax_f": 90.0, "tmin_f": 60.0}],
    }
    out = _convert(fc, "C")
    assert out["current"]["temp_c"] == 25.0
    assert "temp_f" not in out["current"]
    assert out["hourly"][0]["temp_c"] == 25.0
    assert out["daily"][0]["tmax_c"] == 32.2
    assert out["daily"][0]["tmin_c"] == 15.6
    outf = _convert(fc, "F")
    assert outf["current"]["temp_f"] == 77.0
    assert "temp_c" not in outf["current"]


def test_backup_unsafe_zip_leaves_everything_alone():
    """An unsafe path in a backup zip used to 400 AFTER the upload dir was
    already wiped. Now the garden must be untouched."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    probe = UPLOAD_DIR / "audit-probe.txt"
    probe.write_text("still here")
    manifest = {"format": "verdant-backup", "format_version": 1, "tables": {}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps(manifest))
        zf.writestr("files/ok.txt", "fine")
        zf.writestr("files/../../evil.txt", "zip-slip")
    buf.seek(0)
    r = client.post(
        "/api/backup/import",
        files={"file": ("evil.zip", buf, "application/zip")},
    )
    assert r.status_code == 400, r.text
    assert probe.is_file(), "upload dir was wiped before the zip was validated"
    assert not (UPLOAD_DIR / "ok.txt").exists()


def test_bulk_delete_posts_removed():
    """DELETE /api/posts (clear_posts: wipe every post, no guard) was
    removed at Josh's request. Single-post DELETE still works."""
    r = client.post("/api/posts", json={"title": "Keep me", "content": "x"})
    assert r.status_code in (200, 201), r.text
    post_id = r.json()["id"]
    r = client.request("DELETE", "/api/posts")
    assert r.status_code == 405, r.text
    # the post survived, and per-post delete still works
    assert client.get(f"/api/posts/{post_id}").status_code == 200
    assert client.delete(f"/api/posts/{post_id}").status_code == 204
