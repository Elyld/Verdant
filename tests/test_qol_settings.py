"""Regression tests for the release QoL settings (feature/release-visuals).

New keys: week_start, default_weight_unit, slideshow_interval,
confirm_water_all. Run with:  pytest -q
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="qol-settings-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import UPLOAD_DIR, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _put(**kwargs):
    payload = {
        "zone": "",
        "frost_date": "",
        "last_frost_date": "",
        "digest_enabled": False,
        "discord_webhook_url": "",
        "digest_time": "08:00",
        "temperature_unit": "F",
        "week_start": "0",
        "default_weight_unit": "oz",
        "slideshow_interval": 5,
        "confirm_water_all": True,
    }
    payload.update(kwargs)
    return client.put("/api/settings", json=payload)


def test_settings_defaults_include_new_keys():
    r = client.get("/api/settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["week_start"] == "0"
    assert body["default_weight_unit"] == "oz"
    assert body["slideshow_interval"] == 5
    assert body["confirm_water_all"] is True


def test_settings_round_trip():
    r = _put(week_start="1", default_weight_unit="g", slideshow_interval=30,
             confirm_water_all=False)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["week_start"] == "1"
    assert body["default_weight_unit"] == "g"
    assert body["slideshow_interval"] == 30
    assert body["confirm_water_all"] is False
    # persisted, not just echoed
    assert client.get("/api/settings").json()["week_start"] == "1"
    # restore defaults for other tests
    _put()


def test_settings_reject_bad_week_start():
    r = _put(week_start="2")
    assert r.status_code == 400, r.text


def test_settings_reject_bad_weight_unit():
    r = _put(default_weight_unit="ton")
    assert r.status_code == 400, r.text


def test_settings_reject_bad_slideshow_interval():
    r = _put(slideshow_interval=7)
    assert r.status_code == 400, r.text
