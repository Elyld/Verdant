"""v2.34.0 QoL batch: Today view, planting calculator, undo backends.

Run with:  PYTHONPATH=. python -m pytest -q   (shares the temp DB)
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="today-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import planting  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)

TODAY = date.today()


# ── pure planting math ──────────────────────────────────────────────

def test_match_crop_variety_wins():
    m = planting.match_crop("Cherokee Purple tomato")
    assert m is not None
    assert m["crop_name"] == "Tomato"
    assert m["variety_name"] == "Cherokee Purple"
    assert m["days_to_maturity"] == 80


def test_match_crop_alias():
    m = planting.match_crop("bush beans")
    assert m is not None
    assert m["crop_name"] == "Bean (Bush)"
    assert m["days_to_maturity"] == 50


def test_match_crop_no_match():
    assert planting.match_crop("xyzzy plugh") is None
    assert planting.match_crop("") is None


def test_last_safe_sow_date():
    # Oct 15 frost − 75d maturity − 14d buffer = Jul 18
    assert planting.last_safe_sow_date(date(2026, 10, 15), 75) == date(2026, 7, 18)


def test_sow_verdict_boundaries():
    assert planting.sow_verdict(TODAY + timedelta(days=30), TODAY) == "still_time"
    assert planting.sow_verdict(TODAY + timedelta(days=14), TODAY) == "still_time"
    assert planting.sow_verdict(TODAY + timedelta(days=13), TODAY) == "close"
    assert planting.sow_verdict(TODAY, TODAY) == "close"
    assert planting.sow_verdict(TODAY - timedelta(days=1), TODAY) == "too_late"


def test_harvest_forecast_ready():
    fc = planting.harvest_forecast("Cherokee Purple", "Tomato", TODAY - timedelta(days=90), None, today=TODAY)
    assert fc is not None
    assert fc["days_to_maturity"] == 80
    assert fc["status"] == "ready"
    assert fc["days_until_ready"] == -10


def test_harvest_forecast_growing_and_plant_override():
    fc = planting.harvest_forecast("Lettuce", "Lettuce", TODAY - timedelta(days=10), 45, today=TODAY)
    assert fc is not None
    assert fc["days_to_maturity"] == 45  # plant-level override wins
    assert fc["status"] == "growing"
    assert fc["days_until_ready"] == 35


def test_harvest_forecast_unknown():
    assert planting.harvest_forecast("Mystery", "Xyzzy", None, None, today=TODAY) is None
    assert planting.harvest_forecast("Mystery", "Xyzzy", TODAY, None, today=TODAY) is None


# ── helpers ─────────────────────────────────────────────────────────

def _make_plant(name, **kwargs):
    payload = {"variety_name": name, "species_type": kwargs.pop("species_type", "Tomato")}
    payload.update(kwargs)
    r = client.post("/api/plants/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _delete_plant(pid):
    assert client.delete(f"/api/plants/{pid}").status_code == 204


@pytest.fixture()
def frost_date():
    """Set an exact frost date for one test, restore the old value after."""
    from sqlalchemy.orm import Session as SQLSession

    from app import frost as frost_mod

    with SQLSession(engine) as session:
        old = frost_mod.get_setting(session, "frost_date")
    yield old
    with SQLSession(engine) as session:
        frost_mod.set_setting(session, "frost_date", old)
        session.commit()


def _set_frost(value: str):
    from sqlalchemy.orm import Session as SQLSession

    from app import frost as frost_mod

    with SQLSession(engine) as session:
        frost_mod.set_setting(session, "frost_date", value)
        session.commit()


# ── /api/crops/sow-by ──────────────────────────────────────────────

def test_sow_by_no_frost_date(frost_date):
    _set_frost("")
    body = client.get("/api/crops/sow-by", params={"days_to_maturity": 75}).json()
    assert body["verdict"] == "no_frost_date"
    assert body["sow_by"] is None


def test_sow_by_verdicts(frost_date):
    # frost 100 days out (crosses the year line), 75d maturity:
    # sow_by = today+11 → close
    _set_frost((TODAY + timedelta(days=100)).isoformat())
    body = client.get("/api/crops/sow-by", params={"days_to_maturity": 75}).json()
    assert body["verdict"] == "close"
    assert body["days_left"] == 11
    assert body["buffer_days"] == 14
    # frost 200 days out → still_time
    _set_frost((TODAY + timedelta(days=200)).isoformat())
    body = client.get("/api/crops/sow-by", params={"days_to_maturity": 75}).json()
    assert body["verdict"] == "still_time"
    assert body["days_left"] == 111
    # frost 30 days out, 75d maturity → sow_by was 59 days ago → too_late
    _set_frost((TODAY + timedelta(days=30)).isoformat())
    body = client.get("/api/crops/sow-by", params={"days_to_maturity": 75}).json()
    assert body["verdict"] == "too_late"
    assert body["days_left"] == -59
    # garlic: annualized frost keeps the fall-planted answer sane —
    # 240d maturity can't beat an Oct frost for a *fall* harvest
    _set_frost("2026-10-15")
    body = client.get("/api/crops/sow-by", params={"days_to_maturity": 240}).json()
    assert body["verdict"] == "too_late"
    assert body["frost_date"] == "2026-10-15"


# ── /api/today ─────────────────────────────────────────────────────

def test_today_due_and_forecast(frost_date):
    _set_frost((TODAY + timedelta(days=30)).isoformat())
    loc = _make_location(client)
    plant = _make_plant(
        "Today Test Tomato",
        location_id=loc["id"],
        water_every_days=2,
        date_planted=(TODAY - timedelta(days=90)).isoformat(),
    )
    try:
        # last watered 5 days ago, cadence 2 → overdue
        w = client.post(
            "/api/watering-logs/",
            json={"plant_id": plant["id"], "location_id": loc["id"],
                  "date": (TODAY - timedelta(days=5)).isoformat()},
        )
        assert w.status_code == 201, w.text
        wid = w.json()["id"]
        body = client.get("/api/today").json()
        assert body["ok"] is True
        assert body["date"] == TODAY.isoformat()
        due_names = [(d["plant_name"], d["kind"], d["status"]) for d in body["due"]]
        assert ("Today Test Tomato", "water", "overdue") in due_names
        fc = [f for f in body["harvest_forecast"] if f["plant_id"] == plant["id"]]
        assert len(fc) == 1
        assert fc[0]["status"] == "ready"
        assert fc[0]["days_to_maturity"] == 75  # Tomato guide
        assert body["frost"] is not None
        assert body["frost"]["days_until"] == 30
    finally:
        client.delete(f"/api/watering-logs/{wid}")
        _delete_plant(plant["id"])
        client.delete(f"/api/locations/{loc['id']}")


def test_today_empty_ok():
    body = client.get("/api/today").json()
    assert body["ok"] is True
    assert isinstance(body["due"], list)
    assert isinstance(body["harvest_forecast"], list)
    body = client.get("/api/today").json()
    assert body["ok"] is True
    assert isinstance(body["due"], list)
    assert isinstance(body["harvest_forecast"], list)


# ── undo backends (the toast calls these) ──────────────────────────

def _make_location(client, name="Today Test Bed"):
    r = client.post("/api/locations/", params={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_undo_watering_log():
    loc = _make_location(client)
    plant = _make_plant("Undo Water Tomato", location_id=loc["id"])
    try:
        created = client.post(
            "/api/watering-logs/",
            json={"plant_id": plant["id"], "location_id": loc["id"], "date": TODAY.isoformat()},
        )
        assert created.status_code == 201, created.text
        created = created.json()
        assert client.delete(f"/api/watering-logs/{created['id']}").status_code == 204
        remaining = client.get("/api/watering-logs/", params={"date": TODAY.isoformat()}).json()
        assert all(w["id"] != created["id"] for w in remaining)
    finally:
        _delete_plant(plant["id"])
        client.delete(f"/api/locations/{loc['id']}")


def test_undo_harvest():
    plant = _make_plant("Undo Harvest Tomato")
    try:
        created = client.post(
            "/api/harvests/",
            json={"plant_id": plant["id"], "date": TODAY.isoformat(), "quantity": 3},
        ).json()
        assert client.delete(f"/api/harvests/{created['id']}").status_code == 204
        assert client.get(f"/api/harvests/{created['id']}").status_code == 404
    finally:
        _delete_plant(plant["id"])


def test_undo_observation_note():
    plant = _make_plant("Undo Note Tomato")
    try:
        created = client.post(
            "/api/observations",
            json={"plant_id": plant["id"], "plant_name": plant["variety_name"],
                  "date": TODAY.isoformat(), "notes": "undo me", "health_scale": 7},
        ).json()
        assert client.delete(f"/api/observations/{created['id']}").status_code == 204
        assert client.get(f"/api/observations/{created['id']}").status_code == 404
    finally:
        _delete_plant(plant["id"])
