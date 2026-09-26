"""Weather forecast, garden alerts, and the yield heatmap.

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from datetime import date
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="weather-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402

from app import garden_alerts  # noqa: E402
from app import weather as weather_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Container, PestLog, Plant, Planting, WateringLog  # noqa: E402

init_db()
client = TestClient(app)

TODAY = date(2026, 9, 26)
YEAR = 2026


# --------------------------------------------------------------------------- #
# Forecast fetch + cache (network stubbed)
# --------------------------------------------------------------------------- #
def _canned_payload():
    hours = [f"2026-09-26T{h:02d}:00" for h in range(16, 24)] + \
            [f"2026-09-27T{h:02d}:00" for h in range(24)] + \
            [f"2026-09-28T{h:02d}:00" for h in range(16)]
    n = len(hours)
    return {
        "current": {
            "time": "2026-09-26T16:50", "temperature_2m": 78.2,
            "relative_humidity_2m": 55, "weather_code": 2,
            "wind_speed_10m": 12.0, "wind_gusts_10m": 21.0,
        },
        "hourly": {
            "time": hours,
            "temperature_2m": [78.0] * n,
            "precipitation_probability": [10] * n,
            "precipitation": [0.0] * n,
            "relative_humidity_2m": [55] * n,
            "wind_gusts_10m": [15.0] * n,
        },
        "daily": {
            "time": ["2026-09-26", "2026-09-27", "2026-09-28"],
            "temperature_2m_max": [88.0, 90.0, 84.0],
            "temperature_2m_min": [62.0, 64.0, 60.0],
            "precipitation_probability_max": [20, 10, 40],
            "precipitation_sum": [0.0, 0.0, 0.1],
            "wind_gusts_10m_max": [21.0, 18.0, 25.0],
        },
    }


class _FakeResp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _stub_urlopen(monkeypatch, payload=None, calls=None, fail=False):
    def fake(request, timeout=10):
        if calls is not None:
            calls.append(1)
        if fail:
            raise OSError("network down")
        return _FakeResp(payload if payload is not None else _canned_payload())
    monkeypatch.setattr(weather_mod.urllib.request, "urlopen", fake)
    monkeypatch.setenv("GARDEN_LAT", "38.9")
    monkeypatch.setenv("GARDEN_LON", "-94.7")
    weather_mod._forecast_cache["at"] = 0.0
    weather_mod._forecast_cache["data"] = None


def test_fetch_forecast_compacts_payload(monkeypatch):
    _stub_urlopen(monkeypatch)
    fc = weather_mod.fetch_forecast()
    assert fc["as_of"] == "2026-09-26T16:50"
    assert fc["current"]["temp_f"] == 78.2
    assert fc["current"]["summary"] == "Partly cloudy"
    assert len(fc["hourly"]) == 48
    assert fc["hourly"][0]["gust_mph"] == 15.0
    assert len(fc["daily"]) == 3
    assert fc["daily"][1]["tmax_f"] == 90.0


def test_get_forecast_caches_and_falls_back_to_stale(monkeypatch):
    calls = []
    _stub_urlopen(monkeypatch, calls=calls)
    first = weather_mod.get_forecast()
    second = weather_mod.get_forecast()
    assert first is second  # cache hit — no second network call
    assert len(calls) == 1
    # Now break the network with an expired cache: stale data is returned.
    weather_mod._forecast_cache["at"] = 0.0
    _stub_urlopen(monkeypatch, calls=calls, fail=True)
    weather_mod._forecast_cache["data"] = first
    assert weather_mod.get_forecast() is first


def test_forecast_endpoint_not_configured_without_coords(monkeypatch):
    monkeypatch.delenv("GARDEN_LAT", raising=False)
    monkeypatch.delenv("GARDEN_LON", raising=False)
    r = client.get("/api/weather/forecast")
    assert r.status_code == 200
    assert r.json()["ok"] is False
    r = client.get("/api/weather/alerts")
    assert r.json() == {"ok": False, "reason": "not-configured", "alerts": []}


# --------------------------------------------------------------------------- #
# Alerts linked to garden data
# --------------------------------------------------------------------------- #
def _seed_alert_garden():
    with SQLSession(engine) as s:
        hab = Plant(variety_name="Habanero", species_type="Capsicum chinense",
                    family_genus="Solanaceae")
        tom = Plant(variety_name="Sungold", species_type="Solanum lycopersicum",
                    family_genus="Solanaceae")
        s.add(hab)
        s.add(tom)
        s.flush()
        bag = Container(name="Patio Bag 1", kind="grow bag", season_year=YEAR)
        arch = Container(name="Cattle Arch", kind="arch", season_year=YEAR)
        s.add(bag)
        s.add(arch)
        s.flush()
        s.add(Planting(container_id=bag.id, plant_id=hab.id, season_year=YEAR))
        s.add(Planting(container_id=arch.id, plant_id=tom.id, season_year=YEAR))
        s.add(WateringLog(date=TODAY.isoformat(), amount="2 gal"))
        s.add(PestLog(date="2026-09-25", pest_name="Aphids", plant_id=hab.id,
                      treatment="Neem oil"))
        s.commit()


def _fc(temp=75.0, rh=50, precip=0.0, gust=15.0):
    hours = [{
        "t": f"2026-09-26T{h:02d}:00", "temp_f": temp, "precip_prob": 10,
        "precip_in": precip, "rh": rh, "gust_mph": gust,
    } for h in range(48)]
    return {"as_of": "2026-09-26T16:50",
            "current": {"temp_f": temp}, "hourly": hours, "daily": []}


def _alerts(fc):
    with SQLSession(engine) as s:
        return garden_alerts.compute_alerts(s, fc, today=TODAY)


def test_frost_alert_names_tender_containers():
    _seed_alert_garden()
    alerts = _alerts(_fc(temp=30.0))
    frost = [a for a in alerts if "Frost" in a["title"]]
    assert len(frost) == 1
    assert frost[0]["level"] == "critical"
    assert "Patio Bag 1" in frost[0]["detail"]
    assert "Cattle Arch" in frost[0]["detail"]


def test_no_frost_alert_when_mild():
    alerts = _alerts(_fc(temp=55.0))
    assert not [a for a in alerts if "Frost" in a["title"]]


def test_heat_rain_wind_and_washoff_alerts():
    alerts = _alerts(_fc(temp=97.0, precip=0.05, gust=35.0))
    by_title = {a["title"]: a for a in alerts}
    heat = next(a for a in alerts if "Heat" in a["title"])
    assert heat["level"] == "warn" and "Patio Bag 1" in heat["detail"]
    skip = next(a for a in alerts if "skip watering" in a["title"])
    assert "watered" in skip["detail"].lower()
    wash = next(a for a in alerts if "wash off" in a["title"])
    assert "Neem oil" in wash["title"] and "Habanero" in wash["detail"]
    wind = next(a for a in alerts if "High wind" in a["title"])
    assert "Cattle Arch" in wind["detail"]


def test_blight_watch_for_tomatoes_in_humid_heat():
    alerts = _alerts(_fc(temp=76.0, rh=90))
    blight = [a for a in alerts if "Blight" in a["title"]]
    assert len(blight) == 1
    assert blight[0]["level"] == "info"


def test_is_tender_matches_peppers_and_tomatoes():
    with SQLSession(engine) as s:
        hab = s.query(Plant).filter(Plant.variety_name == "Habanero").first()
        assert garden_alerts.is_tender(hab)
        assert not garden_alerts.is_tender(
            Plant(variety_name="Kale", species_type="Brassica oleracea",
                  family_genus="Brassicaceae"))


# --------------------------------------------------------------------------- #
# Yield heatmap
# --------------------------------------------------------------------------- #
def test_yield_map_totals_weight_per_container():
    r = client.post("/api/plants/", json={
        "variety_name": "Yield Pepper", "species_type": "Capsicum annuum",
        "family_genus": "Solanaceae"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post("/api/containers/", json={
        "name": "Yield Bag", "kind": "grow bag", "season_year": 2031})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = client.post("/api/containers/plantings", json={
        "container_id": cid, "plant_id": pid, "season_year": 2031})
    assert r.status_code == 201, r.text
    for weight, unit in [(16, "oz"), (8, "oz"), (100, "g")]:
        r = client.post("/api/harvests/", json={
            "plant_id": pid, "date": "2031-08-01", "quantity": 1,
            "weight": weight, "weight_unit": unit})
        assert r.status_code == 201, r.text
    r = client.get("/api/containers/yield-map?year=2031")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unit"] == "oz"
    # 16 + 8 + 100g(≈3.5oz), and the 2026-seeded harvests must not leak in.
    assert abs(body["totals"]["Yield Bag"] - 27.5) < 0.1
    r = client.get("/api/containers/yield-map?year=1999")
    assert r.json()["totals"] == {}
