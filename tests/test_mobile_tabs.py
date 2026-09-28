"""Validation tests for the mobile_tabs setting (nav refresh, v2.28.0).

mobile_tabs is stored as a JSON array string of tab keys (max 4, deduped,
order preserved). PUT /api/settings must 400 on a bad key or >4 tabs.
Run with:  pytest -q
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="mobile-tabs-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import UPLOAD_DIR, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.settings import (  # noqa: E402
    DEFAULT_MOBILE_TABS,
    MOBILE_TAB_KEYS,
    normalize_mobile_tabs,
)

init_db()
client = TestClient(app)

BASE_PAYLOAD = {
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
    "garden_lat": "",
    "garden_lon": "",
}


def _put(mobile_tabs):
    payload = dict(BASE_PAYLOAD, mobile_tabs=mobile_tabs)
    return client.put("/api/settings", json=payload)


def test_mobile_tabs_defaults_unset():
    body = client.get("/api/settings").json()
    assert body["mobile_tabs"] == ""
    assert set(DEFAULT_MOBILE_TABS) <= MOBILE_TAB_KEYS


def test_mobile_tabs_bad_key_400():
    r = _put(json.dumps(["quick", "nope"]))
    assert r.status_code == 400, r.text


def test_mobile_tabs_too_many_400():
    r = _put(json.dumps(["quick", "plants", "calendar", "planner", "costs"]))
    assert r.status_code == 400, r.text


def test_mobile_tabs_not_json_400():
    r = _put("not-json")
    assert r.status_code == 400, r.text


def test_mobile_tabs_not_a_list_400():
    r = _put(json.dumps("quick"))
    assert r.status_code == 400, r.text


def test_mobile_tabs_valid_roundtrip_and_dedupe():
    r = _put(json.dumps(["planner", "costs", "planner", "seeds"]))
    assert r.status_code == 200, r.text
    body = client.get("/api/settings").json()
    assert json.loads(body["mobile_tabs"]) == ["planner", "costs", "seeds"]


def test_mobile_tabs_cleared():
    _put(json.dumps(["quick"]))
    r = _put("")
    assert r.status_code == 200, r.text
    assert client.get("/api/settings").json()["mobile_tabs"] == ""


def test_normalize_mobile_tabs_unit():
    assert normalize_mobile_tabs("") == ""
    assert normalize_mobile_tabs("  ") == ""
    assert json.loads(normalize_mobile_tabs('["seeds","quick","seeds"]')) == ["seeds", "quick"]
