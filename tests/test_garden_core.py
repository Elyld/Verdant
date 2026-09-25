"""Garden-core API tests: plants, timeline, reminders, harvests, review.

Run with:  pytest -q      (shares the same temp DB as test_api.py)
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="garden-core-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

TODAY = date.today()


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def location(client):
    res = client.post("/api/locations/", params={"name": "Test bed"})
    assert res.status_code == 201, res.text
    return res.json()


def make_plant(client, name, location_id=None, **kwargs):
    payload = {"variety_name": name, "species_type": "Test species"}
    if location_id:
        payload["location_id"] = location_id
    payload.update(kwargs)
    res = client.post("/api/plants/", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- #
def test_plant_crud_with_cadence(client):
    plant = make_plant(client, "Cadence Tomato", water_every_days=3, feed_every_days=14)
    assert plant["plant_id"].startswith("PLANT-")
    assert plant["water_every_days"] == 3
    assert plant["feed_every_days"] == 14

    patched = client.patch(f"/api/plants/{plant['id']}", json={"water_every_days": 5}).json()
    assert patched["water_every_days"] == 5

    assert any(p["id"] == plant["id"] for p in client.get("/api/plants/").json())
    assert client.delete(f"/api/plants/{plant['id']}").status_code == 204
    assert client.get(f"/api/plants/{plant['id']}").status_code == 404


def test_new_pages_render(client):
    for path, marker in (("/plants", 'id="plant-grid"'), ("/review", 'id="review-year"')):
        res = client.get(path)
        assert res.status_code == 200, path
        assert "Verdant" in res.text
        assert marker in res.text
        primary_tag = res.text.split(marker, 1)[1].split(">", 1)[0]
        assert "hidden" not in primary_tag


def test_harvest_create_links_to_plant(client):
    plant = make_plant(client, "Harvest Pepper")
    res = client.post(
        "/api/harvests/",
        json={"plant_id": plant["id"], "date": str(TODAY), "quantity": 3, "unit": "fruit", "weight": 12.5},
    )
    assert res.status_code == 201, res.text
    harvest = res.json()
    assert isinstance(harvest["id"], int)
    assert harvest["plant_id"] == plant["id"]
    assert harvest["weight"] == 12.5

    bad = client.post(
        "/api/harvests/",
        json={"plant_id": 999999, "date": str(TODAY), "quantity": 1},
    )
    assert bad.status_code == 404


def test_watering_log_with_plant_inherits_location(client, location):
    plant = make_plant(client, "Water Basil", location_id=location["id"])
    res = client.post("/api/watering-logs/", json={"plant_id": plant["id"], "date": str(TODAY)})
    assert res.status_code == 201, res.text
    log = res.json()
    assert log["plant_id"] == plant["id"]
    assert log["location_id"] == location["id"]

    # plant with no location at all is rejected
    loner = make_plant(client, "Lonely Cactus")
    bad = client.post("/api/watering-logs/", json={"plant_id": loner["id"], "date": str(TODAY)})
    assert bad.status_code == 400


def test_observation_linked_has_weather_fields(client):
    plant = make_plant(client, "Weather Lettuce")
    res = client.post(
        "/api/observations",
        json={"date": str(TODAY), "plant_name": "Lettuce", "plant_id": plant["id"], "health_scale": 9},
    )
    assert res.status_code == 201, res.text
    obs = res.json()
    # weather is best-effort (no network in tests), but the fields must exist
    assert "temp_c" in obs and "weather_summary" in obs


def test_fertilization_links_to_plant(client):
    plant = make_plant(client, "Fed Kale")
    res = client.post(
        "/api/fertilizations",
        json={"date": str(TODAY), "fertilizer_name": "Kelp meal", "plant_id": plant["id"]},
    )
    assert res.status_code == 201, res.text
    assert res.json()["plant_id"] == plant["id"]


def test_reminder_statuses(client, location):
    # No location: nothing can water it implicitly, so never-watered + cadence -> overdue.
    overdue = make_plant(client, "Overdue Okra", water_every_days=7)
    # never watered + cadence set -> overdue
    fresh = make_plant(client, "Fresh Fennel", location_id=location["id"], water_every_days=7)
    client.post("/api/watering-logs/", json={"plant_id": fresh["id"], "date": str(TODAY)})
    noschedule = make_plant(client, "Nosched Nettle")

    reminders = client.get("/api/plants/reminders/list").json()
    by_id = {(r["plant_id"], r["kind"]): r for r in reminders}

    assert by_id[(overdue["id"], "water")]["status"] == "overdue"
    ok = by_id[(fresh["id"], "water")]
    assert ok["status"] == "ok"
    assert ok["days_until_due"] == 7
    assert by_id[(noschedule["id"], "water")]["status"] == "unset"

    # overdue reminder carries the plant name for display
    assert by_id[(overdue["id"], "water")]["plant_name"] == "Overdue Okra"


def test_timeline_aggregates_all_event_kinds(client, location):
    plant = make_plant(client, "Timeline Thyme", location_id=location["id"])
    pid = plant["id"]
    day = TODAY - timedelta(days=2)

    client.post(
        "/api/observations",
        json={"date": str(day), "plant_name": "Thyme", "plant_id": pid, "health_scale": 8},
    )
    client.post("/api/fertilizations", json={"date": str(day), "fertilizer_name": "Compost tea", "plant_id": pid})
    client.post("/api/harvests/", json={"plant_id": pid, "date": str(day), "quantity": 2})
    client.post("/api/watering-logs/", json={"plant_id": pid, "date": str(day)})

    tl = client.get(f"/api/plants/{pid}/timeline").json()
    assert tl["plant_name"] == "Timeline Thyme"
    kinds = {e["kind"] for e in tl["events"]}
    assert kinds == {"observation", "fertilization", "harvest", "watering"}
    # newest first
    dates = [e["date"] for e in tl["events"]]
    assert dates == sorted(dates, reverse=True)
    assert tl["photos"] == []  # no images uploaded in this test

    assert client.get("/api/plants/999999/timeline").status_code == 404


def test_review_endpoint(client):
    year = TODAY.year
    data = client.get(f"/api/stats/review?year={year}").json()
    assert data["year"] == year
    assert len(data["observations_by_month"]) == 12
    assert len(data["avg_health_by_month"]) == 12
    assert data["harvest_count"] >= 1  # seeded by test_harvest_create_links_to_plant
    assert data["observations"] >= 1
    assert isinstance(data["top_plants"], list)
    assert "busiest_day" in data and "busiest_day_count" in data
