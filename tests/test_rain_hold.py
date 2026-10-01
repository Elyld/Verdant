"""Weather-aware care tests: watering reminders hold when rain is coming.

Run with:  pytest -q      (shares the same temp DB as test_api.py)
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="rain-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from app import weather as weather_mod  # noqa: E402
from app.database import get_session, init_db  # noqa: E402
from app.models import ObservationLog, Plant, WateringLog  # noqa: E402
from app.routers.digest import _line  # noqa: E402
from app.routers.plants import plant_reminders, rain_hold_note  # noqa: E402


@pytest.fixture(scope="module")
def session():
    init_db()
    s = next(get_session())
    plant = Plant(
        variety_name="Rain Test Tomato", species_type="Tomato", status="Growing",
        water_every_days=1, feed_every_days=30,
    )
    s.add(plant)
    s.commit()
    s.refresh(plant)
    # watered yesterday with a daily cadence -> due today; fed long ago -> feed due too
    s.add(WateringLog(plant_id=plant.id, date=(date.today() - timedelta(days=1)).isoformat()))
    s.add(ObservationLog(
        plant_id=plant.id, plant_name="Rain Test Tomato",
        date=(date.today() - timedelta(days=40)).isoformat(), notes="fed",
    ))
    # mark the observation as a feeding? feed cadence uses FertilizationLog; use that instead
    from app.models import FertilizationLog
    s.add(FertilizationLog(
        plant_id=plant.id, date=(date.today() - timedelta(days=40)).isoformat(),
        fertilizer_name="Test Feed",
    ))
    s.commit()
    yield s
    for m in (WateringLog, ObservationLog, FertilizationLog, Plant):
        for row in s.query(m).filter(
            (m.plant_id == plant.id) if hasattr(m, "plant_id") else (m.id == plant.id)
        ).all():
            s.delete(row)
    s.commit()
    s.close()


def _rainy_forecast(inches=0.6, prob=80):
    return {"daily": [
        {"date": date.today().isoformat(), "precip_in": inches, "precip_prob": prob},
        {"date": (date.today() + timedelta(days=1)).isoformat(), "precip_in": 0, "precip_prob": 10},
    ]}


def _dry_forecast():
    return {"daily": [
        {"date": date.today().isoformat(), "precip_in": 0, "precip_prob": 5},
        {"date": (date.today() + timedelta(days=1)).isoformat(), "precip_in": 0, "precip_prob": 5},
    ]}


def test_rain_hold_note_formats(session, monkeypatch):
    monkeypatch.setattr(weather_mod, "get_forecast", lambda session=None: _rainy_forecast())
    note = rain_hold_note(session)
    assert note is not None
    assert '0.6" of rain' in note
    assert "today" in note


def test_rain_hold_note_tomorrow(session, monkeypatch):
    fc = {"daily": [
        {"date": date.today().isoformat(), "precip_in": 0, "precip_prob": 5},
        {"date": (date.today() + timedelta(days=1)).isoformat(), "precip_in": 0.5, "precip_prob": 90},
    ]}
    monkeypatch.setattr(weather_mod, "get_forecast", lambda session=None: fc)
    assert "tomorrow" in (rain_hold_note(session) or "")


def test_rain_hold_note_probability_only(session, monkeypatch):
    monkeypatch.setattr(weather_mod, "get_forecast", lambda session=None: _rainy_forecast(inches=0, prob=85))
    note = rain_hold_note(session)
    assert note is not None and "85% chance" in note


def test_no_hold_when_dry(session, monkeypatch):
    monkeypatch.setattr(weather_mod, "get_forecast", lambda session=None: _dry_forecast())
    assert rain_hold_note(session) is None
    for r in plant_reminders(session):
        assert r.rain_hold is False


def test_no_hold_when_weather_unconfigured(session, monkeypatch):
    monkeypatch.setattr(weather_mod, "get_forecast", lambda session=None: None)
    assert rain_hold_note(session) is None


def test_water_reminder_held_feed_not(session, monkeypatch):
    monkeypatch.setattr(weather_mod, "get_forecast", lambda session=None: _rainy_forecast())
    reminders = plant_reminders(session)
    water = [r for r in reminders if r.kind == "water" and r.plant_name == "Rain Test Tomato"]
    feed = [r for r in reminders if r.kind == "feed" and r.plant_name == "Rain Test Tomato"]
    assert water and water[0].status in ("due", "soon", "overdue")
    assert water[0].rain_hold is True
    assert water[0].rain_note
    assert feed and feed[0].rain_hold is False


def test_digest_line_shows_rain_hold(session, monkeypatch):
    monkeypatch.setattr(weather_mod, "get_forecast", lambda session=None: _rainy_forecast())
    reminders = plant_reminders(session)
    water = next(r for r in reminders if r.kind == "water" and r.plant_name == "Rain Test Tomato")
    line = _line(water)
    assert "🌧" in line
    assert "rain" in line.lower()
