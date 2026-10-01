"""Pantry & preservation tests: CRUD, add-to-pantry flow, use/decrement.

Run with:  pytest -q      (shares the same temp DB as test_api.py)
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="pantry-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import get_session, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Harvest, PantryItem, Plant, PreservationLog  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def plant_and_harvest():
    session = next(get_session())
    plant = Plant(variety_name="Test Tomato", species_type="Tomato", status="Growing")
    session.add(plant)
    session.commit()
    session.refresh(plant)
    harvest = Harvest(plant_id=plant.id, date="2026-09-01", quantity=10, unit="fruit", weight=32, weight_unit="oz")
    session.add(harvest)
    session.commit()
    session.refresh(harvest)
    yield plant, harvest
    # cleanup: shared-DB hygiene
    for item in session.query(PantryItem).all():
        session.delete(item)
    for log in session.query(PreservationLog).all():
        session.delete(log)
    session.delete(harvest)
    session.delete(plant)
    session.commit()
    session.close()


def test_preservation_crud(client, plant_and_harvest):
    plant, harvest = plant_and_harvest
    payload = {
        "date": "2026-09-02",
        "method": "canned",
        "variety_name": "Test Tomato",
        "plant_id": plant.id,
        "harvest_id": harvest.id,
        "qty_in": 12,
        "qty_in_unit": "lbs",
        "qty_out": 7,
        "qty_out_unit": "quarts",
        "stored_location": "pantry shelf",
        "notes": "water bath",
        "add_to_pantry": True,
    }
    r = client.post("/api/pantry/preservation", json=payload)
    assert r.status_code == 201, r.text
    log = r.json()
    assert log["preservation_id"].startswith("PRES-")
    assert log["method"] == "canned"

    # add_to_pantry spawned a pantry item from qty_out
    r = client.get("/api/pantry/items")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["quantity"] == 7
    assert items[0]["unit"] == "quarts"
    assert items[0]["preservation_id"] == log["id"]

    # history lists it
    r = client.get("/api/pantry/preservation")
    assert any(l["id"] == log["id"] for l in r.json())

    # delete the log; the pantry item survives, unlinked
    r = client.delete(f"/api/pantry/preservation/{log['id']}")
    assert r.status_code == 204
    r = client.get("/api/pantry/items")
    items = r.json()
    assert len(items) == 1 and items[0]["preservation_id"] is None


def test_preservation_bad_method_rejected(client):
    r = client.post("/api/pantry/preservation", json={"date": "2026-09-02", "method": "teleported"})
    assert r.status_code == 422


def test_pantry_use_decrements_and_empties(client):
    r = client.post("/api/pantry/items", json={
        "name": "Frozen peppers", "method": "frozen",
        "quantity": 5, "unit": "bags", "stored_date": "2026-08-15",
    })
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]

    r = client.post(f"/api/pantry/items/{item_id}/use", json={"amount": 2})
    assert r.status_code == 200
    assert r.json()["quantity"] == 3

    # using the rest empties it: row gone, tombstone quantity 0
    r = client.post(f"/api/pantry/items/{item_id}/use", json={"amount": 3})
    assert r.status_code == 200
    assert r.json()["quantity"] == 0
    r = client.get("/api/pantry/items")
    assert all(i["id"] != item_id for i in r.json())


def test_pantry_use_missing_item_404(client):
    r = client.post("/api/pantry/items/999999/use", json={"amount": 1})
    assert r.status_code == 404


def test_preservation_without_pantry(client):
    r = client.post("/api/pantry/preservation", json={
        "date": "2026-09-03", "method": "gave_away",
        "variety_name": "Zucchini", "qty_out": 4, "qty_out_unit": "fruit",
        "add_to_pantry": False,
    })
    assert r.status_code == 201, r.text
    r = client.get("/api/pantry/items")
    assert all(i["name"] != "Zucchini" for i in r.json())
    # cleanup of the gave_away log happens in the fixture teardown
    log_id = client.get("/api/pantry/preservation").json()[0]["id"]
    client.delete(f"/api/pantry/preservation/{log_id}")


def test_method_filter(client):
    client.post("/api/pantry/preservation", json={"date": "2026-09-04", "method": "frozen", "variety_name": "Beans"})
    client.post("/api/pantry/preservation", json={"date": "2026-09-04", "method": "canned", "variety_name": "Beans"})
    r = client.get("/api/pantry/preservation", params={"method": "frozen"})
    assert r.status_code == 200
    assert all(l["method"] == "frozen" for l in r.json())
    assert any(l["method"] == "frozen" for l in r.json())
    # cleanup
    for l in client.get("/api/pantry/preservation").json():
        client.delete(f"/api/pantry/preservation/{l['id']}")
