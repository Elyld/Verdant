"""Quick Log harvest weight tests.

The Quick Log harvest flow now POSTs weight/weight_unit alongside quantity;
verify the API persists them (this is the same payload quick.js sends).

Run with:  pytest -q  (from the repo root with PYTHONPATH=.)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="quicklog-weight-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)

_created = {"plants": [], "harvests": []}


def _plant():
    r = client.post("/api/plants/", json={
        "variety_name": "Quicklog Weight Pepper", "species_type": "Pepper",
        "status": "Growing",
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    _created["plants"].append(pid)
    return pid


def teardown_module():
    for h_id in _created["harvests"]:
        client.delete(f"/api/harvests/{h_id}")
    for p_id in _created["plants"]:
        client.delete(f"/api/plants/{p_id}")


def test_harvest_with_weight_persists():
    """Weight + unit from the Quick Log flow are stored on the harvest."""
    pid = _plant()
    r = client.post("/api/harvests/", json={
        "plant_id": pid, "date": "2026-09-27", "quantity": 3,
        "weight": 12.5, "weight_unit": "oz",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    _created["harvests"].append(body["id"])
    assert body["weight"] == 12.5
    assert body["weight_unit"] == "oz"


def test_harvest_weight_unit_normalized():
    """Unit spellings are canonicalized ('LB' -> 'lb', like the Plants form)."""
    pid = _plant()
    r = client.post("/api/harvests/", json={
        "plant_id": pid, "date": "2026-09-27", "quantity": 2,
        "weight": 1.5, "weight_unit": "LB",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    _created["harvests"].append(body["id"])
    assert body["weight_unit"] == "lb"


def test_harvest_without_weight_still_works():
    """Omitting weight (old Quick Log behavior) still creates the harvest."""
    pid = _plant()
    r = client.post("/api/harvests/", json={
        "plant_id": pid, "date": "2026-09-27", "quantity": 1,
        "weight": None, "weight_unit": "oz",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    _created["harvests"].append(body["id"])
    assert body["weight"] is None
    assert body["quantity"] == 1


def test_harvest_weight_in_grams_persists():
    """Metric units persist as-is; conversion happens at read time."""
    pid = _plant()
    r = client.post("/api/harvests/", json={
        "plant_id": pid, "date": "2026-09-27", "quantity": 4,
        "weight": 250, "weight_unit": "g",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    _created["harvests"].append(body["id"])
    assert body["weight"] == 250
    assert body["weight_unit"] == "g"
