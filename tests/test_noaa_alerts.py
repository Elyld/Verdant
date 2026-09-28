"""NOAA / NWS active weather alerts (network stubbed).

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
from urllib.error import URLError

import pytest

TMP = Path(tempfile.mkdtemp(prefix="noaa-test-"))
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


def _set_coords(lat: str, lon: str) -> None:
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "garden_lat", lat)
        frost_mod.set_setting(s, "garden_lon", lon)
        s.commit()


def _session():
    return SQLSession(engine)


@pytest.fixture
def coords():
    _set_coords("39.09", "-95.66")
    yield
    _set_coords("", "")
    weather_mod._noaa_cache.update({"at": 0.0, "data": None, "coords": None})


@pytest.fixture(autouse=True)
def _fresh_noaa_cache():
    weather_mod._noaa_cache.update({"at": 0.0, "data": None, "coords": None})
    yield
    weather_mod._noaa_cache.update({"at": 0.0, "data": None, "coords": None})


def _canned_noaa(*alerts):
    return {"type": "FeatureCollection", "features": [{"properties": a} for a in alerts]}


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub_urlopen(monkeypatch, payload=None, error=None):
    calls = []

    def fake(request, timeout=None):
        calls.append(request.full_url)
        # api.weather.gov requires a User-Agent — assert we send one.
        assert request.get_header("User-agent") or request.get_header("User-Agent"), \
            "missing User-Agent header"
        if error is not None:
            raise error
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(weather_mod.urllib.request, "urlopen", fake)
    return calls


FREEZE_ALERT = {
    "event": "Freeze Warning",
    "headline": "Freeze Warning issued October 12 at 3:15PM CDT",
    "severity": "Severe",
    "onset": "2026-10-13T01:00:00-05:00",
    "ends": "2026-10-13T09:00:00-05:00",
    "description": "* WHAT...Sub-freezing temperatures as low as 28 expected.\n* WHERE...Portions of northeast Kansas.",
}


# --------------------------------------------------------------------------- #
# fetch_noaa_alerts
# --------------------------------------------------------------------------- #
def test_active_alerts_parsed(coords, monkeypatch):
    calls = _stub_urlopen(monkeypatch, _canned_noaa(FREEZE_ALERT))
    alerts = weather_mod.fetch_noaa_alerts(_session())
    assert len(calls) == 1
    assert "point=39.09,-95.66" in calls[0]
    assert len(alerts) == 1
    a = alerts[0]
    assert a["event"] == "Freeze Warning"
    assert a["severity"] == "Severe"
    assert a["onset"] == "2026-10-13T01:00:00-05:00"
    assert a["ends"] == "2026-10-13T09:00:00-05:00"
    assert "Sub-freezing" in a["description"]
    # trimmed shape — no instruction blocks, no geometry, no raw dump
    assert set(a) == {"event", "headline", "severity", "onset", "ends", "description"}


def test_long_description_truncated(coords, monkeypatch):
    long_alert = dict(FREEZE_ALERT, description="word " * 500)
    _stub_urlopen(monkeypatch, _canned_noaa(long_alert))
    alerts = weather_mod.fetch_noaa_alerts(_session())
    assert len(alerts[0]["description"]) <= 601


def test_no_coords_returns_empty(monkeypatch):
    calls = _stub_urlopen(monkeypatch, _canned_noaa(FREEZE_ALERT))
    with _session() as s:
        assert weather_mod.fetch_noaa_alerts(s) == []
    assert calls == []  # no network without coords


def test_http_error_returns_none(coords, monkeypatch):
    _stub_urlopen(monkeypatch, error=URLError("boom"))
    with _session() as s:
        assert weather_mod.fetch_noaa_alerts(s) is None


def test_bad_payload_returns_none(coords, monkeypatch):
    calls = []

    def fake(request, timeout=None):
        calls.append(1)
        return _FakeResponse(b"not json{{{")

    monkeypatch.setattr(weather_mod.urllib.request, "urlopen", fake)
    with _session() as s:
        assert weather_mod.fetch_noaa_alerts(s) is None


# --------------------------------------------------------------------------- #
# get_noaa_alerts cache
# --------------------------------------------------------------------------- #
def test_cache_serves_second_call(coords, monkeypatch):
    calls = _stub_urlopen(monkeypatch, _canned_noaa(FREEZE_ALERT))
    with _session() as s:
        first = weather_mod.get_noaa_alerts(s)
        second = weather_mod.get_noaa_alerts(s)
    assert len(first) == 1 and first == second
    assert len(calls) == 1  # 15-min TTL: one fetch


def test_failed_refresh_serves_stale(coords, monkeypatch):
    calls = _stub_urlopen(monkeypatch, _canned_noaa(FREEZE_ALERT))
    with _session() as s:
        assert len(weather_mod.get_noaa_alerts(s)) == 1
    assert len(calls) == 1
    # expire the cache, then break the network
    weather_mod._noaa_cache["at"] = 0.0
    _stub_urlopen(monkeypatch, error=URLError("boom"))
    with _session() as s:
        stale = weather_mod.get_noaa_alerts(s)
    assert len(stale) == 1  # stale beats blank
    assert stale[0]["event"] == "Freeze Warning"


# --------------------------------------------------------------------------- #
# /api/weather/noaa-alerts endpoint
# --------------------------------------------------------------------------- #
def test_endpoint_with_alerts(coords, monkeypatch):
    _stub_urlopen(monkeypatch, _canned_noaa(FREEZE_ALERT))
    r = client.get("/api/weather/noaa-alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["alerts"]) == 1
    assert body["alerts"][0]["event"] == "Freeze Warning"


def test_endpoint_unconfigured_returns_empty(monkeypatch):
    calls = _stub_urlopen(monkeypatch, _canned_noaa(FREEZE_ALERT))
    r = client.get("/api/weather/noaa-alerts")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "alerts": []}
    assert calls == []


def test_endpoint_service_down_returns_empty_not_500(coords, monkeypatch):
    _stub_urlopen(monkeypatch, error=URLError("boom"))
    r = client.get("/api/weather/noaa-alerts")
    assert r.status_code == 200
    assert r.json()["alerts"] == []
