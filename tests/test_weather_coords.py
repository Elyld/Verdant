"""Garden coordinates as Settings (v2.26.0): Settings beat env vars, env vars
still work as fallback, invalid values fall back gracefully, and the
/api/weather/geolocate endpoint does its one-shot IP lookup.

Run with:  pytest -q
"""
import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="weather-coords-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402

from app import frost as frost_mod  # noqa: E402
from app import weather as weather_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _set_settings_coords(lat: str, lon: str) -> None:
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "garden_lat", lat)
        frost_mod.set_setting(s, "garden_lon", lon)
        s.commit()


def _session():
    return SQLSession(engine)


@pytest.fixture
def clean_coords():
    yield
    _set_settings_coords("", "")


@pytest.fixture
def env_coords(monkeypatch):
    monkeypatch.setenv("GARDEN_LAT", "10.0")
    monkeypatch.setenv("GARDEN_LON", "20.0")
    return ("10.0", "20.0")


def test_settings_coords_win_over_env(clean_coords, env_coords):
    _set_settings_coords("38.9", "-94.7")
    with _session() as s:
        assert weather_mod._coords(s) == (38.9, -94.7)
        assert weather_mod.configured(s) is True


def test_env_fallback_when_settings_unset(clean_coords, env_coords):
    with _session() as s:
        assert weather_mod._coords(s) == (10.0, 20.0)
    # ... and the old no-session call shape keeps working (env only).
    assert weather_mod._coords() == (10.0, 20.0)
    assert weather_mod._coords(None) == (10.0, 20.0)


def test_invalid_settings_fall_back_to_env(clean_coords, env_coords):
    for lat, lon in (("abc", "-94.7"), ("38.9", "xyz"), ("999", "-94.7"),
                     ("38.9", ""), ("", "-94.7")):
        _set_settings_coords(lat, lon)
        with _session() as s:
            assert weather_mod._coords(s) == (10.0, 20.0), (lat, lon)


def test_nothing_configured(clean_coords, monkeypatch):
    monkeypatch.delenv("GARDEN_LAT", raising=False)
    monkeypatch.delenv("GARDEN_LON", raising=False)
    with _session() as s:
        assert weather_mod._coords(s) is None
        assert weather_mod.configured(s) is False
    r = client.get("/api/weather/forecast")
    assert r.json()["ok"] is False
    assert r.json()["reason"] == "not-configured"


def _canned_forecast_payload():
    hours = [f"2026-09-26T{h:02d}:00" for h in range(48)]
    return {
        "current": {"time": "2026-09-26T16:50", "temperature_2m": 78.2,
                    "relative_humidity_2m": 55, "weather_code": 2,
                    "wind_speed_10m": 12.0, "wind_gusts_10m": 21.0},
        "hourly": {"time": hours, "temperature_2m": [78.0] * 48,
                   "precipitation_probability": [10] * 48,
                   "precipitation": [0.0] * 48,
                   "relative_humidity_2m": [55] * 48,
                   "wind_gusts_10m": [15.0] * 48},
        "daily": {"time": ["2026-09-26"] * 7,
                 "temperature_2m_max": [88.0] * 7,
                 "temperature_2m_min": [62.0] * 7,
                 "precipitation_probability_max": [20] * 7,
                 "precipitation_sum": [0.0] * 7,
                 "wind_gusts_10m_max": [18.0] * 7},
    }


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_forecast_endpoint_uses_settings_coords(clean_coords, monkeypatch):
    monkeypatch.delenv("GARDEN_LAT", raising=False)
    monkeypatch.delenv("GARDEN_LON", raising=False)
    _set_settings_coords("38.9", "-94.7")
    seen_urls = []

    def fake(request, timeout=10):
        seen_urls.append(request.full_url)
        return _FakeResp(_canned_forecast_payload())

    monkeypatch.setattr(weather_mod.urllib.request, "urlopen", fake)
    weather_mod._forecast_cache["at"] = 0.0
    weather_mod._forecast_cache["data"] = None
    weather_mod._forecast_cache.pop("coords", None)
    r = client.get("/api/weather/forecast")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert seen_urls and "latitude=38.9" in seen_urls[0]
    assert "longitude=-94.7" in seen_urls[0]


def test_settings_put_validates_coords():
    base = client.get("/api/settings").json()
    base.pop("frost_preview", None)

    bad = dict(base, garden_lat="abc", garden_lon="-94.7")
    assert client.put("/api/settings", json=bad).status_code == 400
    bad = dict(base, garden_lat="38.9", garden_lon="999")
    assert client.put("/api/settings", json=bad).status_code == 400
    bad = dict(base, garden_lat="91", garden_lon="0")
    assert client.put("/api/settings", json=bad).status_code == 400

    good = dict(base, garden_lat="38.90000", garden_lon="-94.70000")
    r = client.put("/api/settings", json=good)
    assert r.status_code == 200, r.text
    assert r.json()["garden_lat"] == "38.90000"
    assert r.json()["garden_lon"] == "-94.70000"

    # Restore whatever was there before.
    restore = dict(base, garden_lat=base.get("garden_lat") or "",
                   garden_lon=base.get("garden_lon") or "")
    r = client.put("/api/settings", json=restore)
    assert r.status_code == 200


def test_get_settings_includes_coords():
    s = client.get("/api/settings").json()
    assert "garden_lat" in s
    assert "garden_lon" in s


def test_geolocate_success(monkeypatch):
    def fake(request, timeout=6):
        assert "ip-api.com" in request.full_url
        return _FakeResp({"status": "success", "lat": 30.2672,
                          "lon": -97.7431, "city": "Austin"})

    monkeypatch.setattr(weather_mod.urllib.request, "urlopen", fake)
    r = client.get("/api/weather/geolocate")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["lat"] == 30.2672
    assert body["lon"] == -97.7431
    assert body["city"] == "Austin"


def test_geolocate_failure_is_graceful(monkeypatch):
    def boom(request, timeout=6):
        raise OSError("network down")

    monkeypatch.setattr(weather_mod.urllib.request, "urlopen", boom)
    r = client.get("/api/weather/geolocate")
    assert r.status_code == 200
    assert r.json() == {"ok": False, "reason": "lookup-failed"}

    def failed_status(request, timeout=6):
        return _FakeResp({"status": "fail", "message": "private range"})

    monkeypatch.setattr(weather_mod.urllib.request, "urlopen", failed_status)
    r = client.get("/api/weather/geolocate")
    assert r.json()["ok"] is False
