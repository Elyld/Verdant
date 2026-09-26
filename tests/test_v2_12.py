"""v2.12.0: seedling tracker — indoor seed-starting workstation."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="garden-v212-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))
os.environ.setdefault("GARDEN_DATABASE_URL", f"sqlite:///{TMP / 'garden.db'}")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _batch(**kw):
    payload = {"variety_name": "Fatalii", "tray": "Tray A", "heat_mat": True, "cells_sown": 12}
    payload.update(kw)
    r = client.post("/api/seedling-batches/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_requires_variety():
    r = client.post("/api/seedling-batches/", json={"tray": "Tray A"})
    assert r.status_code == 422

    b = _batch()
    assert b["batch_id"].startswith("SEEDL-")
    assert b["status"] == "sowing"
    assert b["heat_mat"] is True
    assert b["cells_sown"] == 12


def test_sprout_and_advance_flow():
    b = _batch()

    r = client.post(f"/api/seedling-batches/{b['id']}/sprout?count=4")
    assert r.status_code == 200, r.text
    assert r.json()["germinated"] == 4
    assert r.json()["germination_date"] != ""
    assert r.json()["status"] == "germinating"  # auto-moved out of sowing

    for expected in ["growing", "hardening", "transplanted"]:
        r = client.post(f"/api/seedling-batches/{b['id']}/advance")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == expected
    assert r.json()["transplant_date"] != ""  # stamped on the way out

    r = client.post(f"/api/seedling-batches/{b['id']}/advance")
    assert r.json()["status"] == "finished"
    r = client.post(f"/api/seedling-batches/{b['id']}/advance")
    assert r.status_code == 409  # finished: nowhere left to go


def test_invalid_status_rejected():
    b = _batch()
    r = client.patch(f"/api/seedling-batches/{b['id']}", json={"status": "bogus"})
    assert r.status_code == 422
    r = client.post("/api/seedling-batches/", json={"variety_name": "X", "status": "bogus"})
    assert r.status_code == 422


def test_delete_batch():
    b = _batch()
    r = client.delete(f"/api/seedling-batches/{b['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/api/seedling-batches/{b['id']}").status_code == 404
