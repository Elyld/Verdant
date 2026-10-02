"""Watering-logs API contract: the location precondition on POST.

The OpenAPI schema only marks `date` as required, but a watering must
attach to a location — either `location_id` directly, or `plant_id` for a
plant that has one. That precondition can't be expressed in a flat
`required` list, so the endpoint documents it and fails with a 422 +
FastAPI-style field-level detail (not a business-rule 400) when neither
resolves to a location.

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="watering-logs-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402

from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Location, Plant  # noqa: E402

init_db()
client = TestClient(app)

UID = str(int(time.time() * 1000) % 100000)


@pytest.fixture
def location() -> int:
    with SQLSession(engine) as s:
        loc = Location(name=f"TEST-{UID}-wloc")
        s.add(loc)
        s.commit()
        s.refresh(loc)
        return loc.id


@pytest.fixture
def located_plant(location: int) -> int:
    with SQLSession(engine) as s:
        p = Plant(variety_name=f"TEST-{UID}-wplant", species_type="Tomato",
                  status="Growing", location_id=location)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


@pytest.fixture
def unlocated_plant() -> int:
    with SQLSession(engine) as s:
        p = Plant(variety_name=f"TEST-{UID}-wnoloc", species_type="Basil",
                  status="Growing")
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _detail_entry(resp_json):
    detail = resp_json.get("detail")
    assert isinstance(detail, list) and detail, "expected FastAPI-style detail list"
    return detail[0]


def test_no_location_no_plant_gives_422_with_field_detail():
    r = client.post("/api/watering-logs/", json={"date": "2026-10-02"})
    assert r.status_code == 422, r.text
    entry = _detail_entry(r.json())
    assert entry["loc"] == ["body", "location_id"]
    assert "location" in entry["msg"].lower()
    assert entry["type"] == "value_error"


def test_plant_without_location_gives_422(unlocated_plant: int):
    r = client.post("/api/watering-logs/",
                    json={"date": "2026-10-02", "plant_id": unlocated_plant})
    assert r.status_code == 422, r.text
    assert _detail_entry(r.json())["loc"] == ["body", "location_id"]


def test_plant_with_location_succeeds(located_plant: int, location: int):
    r = client.post("/api/watering-logs/",
                    json={"date": "2026-10-02", "plant_id": located_plant})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["location_id"] == location
    assert body["plant_id"] == located_plant


def test_location_id_directly_succeeds(location: int):
    r = client.post("/api/watering-logs/",
                    json={"date": "2026-10-02", "location_id": location})
    assert r.status_code == 201, r.text
    assert r.json()["location_id"] == location


def test_unknown_plant_still_404s():
    r = client.post("/api/watering-logs/",
                    json={"date": "2026-10-02", "plant_id": 999999999})
    assert r.status_code == 404, r.text


def test_unknown_location_still_404s():
    r = client.post("/api/watering-logs/",
                    json={"date": "2026-10-02", "location_id": 999999999})
    assert r.status_code == 404, r.text
