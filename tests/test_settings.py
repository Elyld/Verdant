"""Settings page API + frost resolution tests.

Shares the same temp DB as the other test modules (see test_api.py); every
test wipes the settings table before and after itself so nothing leaks.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="settings-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, delete  # noqa: E402

from app import frost as frost_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Setting  # noqa: E402
from app.routers.digest import effective_digest_config  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_settings():
    with Session(engine) as s:
        s.exec(delete(Setting))
        s.commit()
    yield
    with Session(engine) as s:
        s.exec(delete(Setting))
        s.commit()


def _session():
    return Session(engine)


def test_settings_round_trip(client):
    res = client.put("/api/settings", json={
        "zone": "6",
        "frost_date": "",
        "last_frost_date": "",
        "digest_enabled": True,
        "discord_webhook_url": "https://discord.example/hook",
        "digest_time": "07:30",
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["zone"] == "6"
    assert body["digest_enabled"] is True
    assert body["digest_time"] == "07:30"

    preview = body["frost_preview"]["first"]
    assert preview["date"] is not None
    assert preview["label"] == "Zone 6 average (approximate)"
    expected = frost_mod.annualize(10, 21)
    assert preview["date"] == expected.isoformat()
    assert preview["days_until"] == (expected - date.today()).days

    # GET reflects the same values
    res = client.get("/api/settings")
    assert res.json()["zone"] == "6"


def test_settings_validation(client):
    base = {
        "zone": "", "frost_date": "", "last_frost_date": "",
        "digest_enabled": False, "discord_webhook_url": "", "digest_time": "08:00",
    }
    for bad in (
        {**base, "zone": "12"},
        {**base, "zone": "6a"},
        {**base, "frost_date": "not-a-date"},
        {**base, "last_frost_date": "2026-13-01"},
        {**base, "digest_time": "8am"},
        {**base, "digest_time": "25:00"},
        {**base, "digest_enabled": True, "discord_webhook_url": ""},
    ):
        res = client.put("/api/settings", json=bad)
        assert res.status_code == 400, bad


def test_frost_precedence_exact_over_zone_over_env(monkeypatch):
    monkeypatch.setenv("FIRST_FROST_DATE", "2026-11-15")
    with _session() as s:
        # nothing set + no env -> unknown
        monkeypatch.delenv("FIRST_FROST_DATE", raising=False)
        frost, source, _ = frost_mod.resolve_frost(s, "first")
        assert (frost, source) == (None, None)
        monkeypatch.setenv("FIRST_FROST_DATE", "2026-11-15")

        # env only -> env wins
        frost, source, _ = frost_mod.resolve_frost(s, "first")
        assert source == "env"
        assert (frost.month, frost.day) == (11, 15)

        # zone beats env
        frost_mod.set_setting(s, "zone", "6")
        s.commit()
        frost, source, zone = frost_mod.resolve_frost(s, "first")
        assert source == "zone" and zone == "6"
        assert (frost.month, frost.day) == (10, 21)

        # exact setting beats zone
        frost_mod.set_setting(s, "frost_date", "2026-10-31")
        s.commit()
        frost, source, _ = frost_mod.resolve_frost(s, "first")
        assert source == "exact"
        assert (frost.month, frost.day) == (10, 31)


def test_frost_unset_returns_nones(monkeypatch):
    monkeypatch.delenv("FIRST_FROST_DATE", raising=False)
    with _session() as s:
        assert frost_mod.resolve_frost(s, "first") == (None, None, None)


def test_frost_annualizes_past_dates():
    with _session() as s:
        frost_mod.set_setting(s, "frost_date", "2001-01-15")
        s.commit()
        frost, source, _ = frost_mod.resolve_frost(s, "first", today=date(2026, 9, 25))
        assert frost == date(2027, 1, 15)
        frost, _, _ = frost_mod.resolve_frost(s, "first", today=date(2026, 1, 10))
        assert frost == date(2026, 1, 15)


def test_zone_maps_are_sane():
    assert frost_mod.ZONE_FIRST_FROST["6"] == (10, 21)
    assert frost_mod.ZONE_LAST_FROST["6"] == (4, 15)
    assert set(frost_mod.VALID_ZONES) == {str(z) for z in range(3, 11)}
    # every zone date annualizes to a real calendar date
    for zone, (m, d) in frost_mod.ZONE_FIRST_FROST.items():
        frost_mod.annualize(m, d)
    for zone, (m, d) in frost_mod.ZONE_LAST_FROST.items():
        frost_mod.annualize(m, d)


def test_effective_digest_config_db_over_env(monkeypatch):
    monkeypatch.setenv("DIGEST_ENABLED", "true")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://env.example/hook")
    monkeypatch.setenv("DIGEST_TIME", "09:00")
    with _session() as s:
        # nothing saved yet -> env rules
        cfg = effective_digest_config(s)
        assert cfg.enabled is True
        assert cfg.webhook_url == "https://env.example/hook"
        assert cfg.time == "09:00"

        # saved settings win, including turning it off
        frost_mod.set_setting(s, "digest_enabled", "false")
        frost_mod.set_setting(s, "discord_webhook_url", "https://db.example/hook")
        frost_mod.set_setting(s, "digest_time", "07:00")
        s.commit()
        cfg = effective_digest_config(s)
        assert cfg.enabled is False
        assert cfg.webhook_url == "https://db.example/hook"
        assert cfg.time == "07:00"


def test_last_frost_zone_lookup():
    with _session() as s:
        frost_mod.set_setting(s, "zone", "7")
        s.commit()
        frost, source, zone = frost_mod.resolve_frost(s, "last")
        assert source == "zone" and zone == "7"
        assert (frost.month, frost.day) == (4, 10)


def test_settings_page_renders(client):
    res = client.get("/settings")
    assert res.status_code == 200
    assert "Verdant · Settings" in res.text
    assert "/static/js/settings.js" in res.text
