"""Morning Discord digest tests: message composition, webhook send, endpoints.

Run with:  pytest -q      (shares the same temp DB as test_api.py)
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="digest-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.digest import (  # noqa: E402
    build_digest_message,
    get_config,
    send_discord_message,
)
from app.routers.plants import ReminderRead  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def rem(plant_id, name, kind, status, days_until_due, last_date=None, due_date=None):
    return ReminderRead(
        plant_id=plant_id, plant_name=name, kind=kind,
        last_date=last_date, due_date=due_date,
        days_until_due=days_until_due, status=status,
    )


def test_message_sections_and_order():
    reminders = [
        rem(1, "Basil", "feed", "due", 0, "2026-09-11", "2026-09-25"),
        rem(2, "Tomato", "water", "overdue", -2, "2026-09-20", "2026-09-23"),
        rem(3, "Pepper", "water", "soon", 1, "2026-09-24", "2026-09-26"),
        rem(4, "Mint", "water", "ok", 10, "2026-09-25", "2026-10-05"),
        rem(5, "Sage", "feed", "unset", None, None, None),
    ]
    msg = build_digest_message(reminders, today=date(2026, 9, 25))
    assert "Morning garden check — Fri Sep 25" in msg
    assert "🔴 **Overdue**" in msg and "**Tomato**" in msg and "2d overdue" in msg
    assert "🟡 **Due today**" in msg and "**Basil**" in msg
    assert "🟢 **Coming up**" in msg and "**Pepper**" in msg
    # ok/unset reminders are not actionable -> excluded
    assert "Mint" not in msg and "Sage" not in msg
    # sections in the right order
    assert msg.index("Overdue") < msg.index("Due today") < msg.index("Coming up")
    # kind icons + last-date context
    assert "💧 **Tomato** — water" in msg and "(last 2026-09-20)" in msg
    assert "🧪 **Basil** — feed" in msg


def test_message_all_clear():
    msg = build_digest_message([rem(1, "Mint", "water", "ok", 10)], today=date(2026, 9, 25))
    assert "All clear" in msg


def test_config_defaults_disabled(monkeypatch):
    monkeypatch.delenv("DIGEST_ENABLED", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DIGEST_TIME", raising=False)
    cfg = get_config()
    assert cfg.enabled is False
    assert cfg.webhook_url == ""
    assert cfg.time == "08:00"


def test_config_enabled(monkeypatch):
    monkeypatch.setenv("DIGEST_ENABLED", "true")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/abc")
    monkeypatch.setenv("DIGEST_TIME", "07:30")
    cfg = get_config()
    assert cfg.enabled is True
    assert cfg.time == "07:30"


def test_send_posts_to_webhook(monkeypatch):
    calls = {}

    class FakeResp:
        status_code = 204
        text = ""

    def fake_post(url, json=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        return FakeResp()

    monkeypatch.setattr("app.routers.digest.httpx.post", fake_post)
    send_discord_message("https://discord.com/api/webhooks/abc", "hello garden")
    assert calls["url"] == "https://discord.com/api/webhooks/abc"
    assert calls["json"] == {"content": "hello garden"}


def test_send_rejects_bad_url():
    with pytest.raises(ValueError):
        send_discord_message("http://not-https.example/x", "hi")


def test_preview_endpoint(client):
    res = client.get("/api/digest/preview")
    assert res.status_code == 200
    assert "Morning garden check" in res.json()["message"]


def test_send_endpoint_requires_config(client, monkeypatch):
    monkeypatch.delenv("DIGEST_ENABLED", raising=False)
    res = client.post("/api/digest/send")
    assert res.status_code == 400
    assert "disabled" in res.json()["detail"]


def test_send_endpoint_sends(client, monkeypatch):
    monkeypatch.setenv("DIGEST_ENABLED", "true")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/abc")
    sent = {}

    def fake_run_digest(session, webhook_url):
        sent["url"] = webhook_url
        return "fake message"

    monkeypatch.setattr("app.routers.digest.run_digest", fake_run_digest)
    res = client.post("/api/digest/send")
    assert res.status_code == 200, res.text
    assert res.json()["sent"] is True
    assert sent["url"] == "https://discord.com/api/webhooks/abc"


def _set_settings_via_db(**kwargs):
    from sqlmodel import Session as _Session

    from app import frost as frost_mod  # noqa: E402
    from app.database import engine as _engine  # noqa: E402

    with _Session(_engine) as s:
        for k, v in kwargs.items():
            frost_mod.set_setting(s, k, v)
        s.commit()


def test_effective_config_picks_timezone():
    from app.routers.digest import effective_digest_config  # noqa: E402
    from sqlmodel import Session as _Session  # noqa: E402

    from app.database import engine as _engine  # noqa: E402

    _set_settings_via_db(digest_timezone="America/Chicago")
    try:
        with _Session(_engine) as s:
            assert effective_digest_config(s).timezone == "America/Chicago"
    finally:
        _set_settings_via_db(digest_timezone="")


def test_resolve_digest_timezone():
    from datetime import datetime  # noqa: E402

    from app.routers.digest import resolve_digest_timezone  # noqa: E402

    local = datetime.now().astimezone().tzinfo
    assert resolve_digest_timezone("America/Chicago").key == "America/Chicago"
    assert resolve_digest_timezone("") == local
    # Invalid names fall back to server local instead of raising.
    assert resolve_digest_timezone("Not/AZone") == local


def test_save_rearms_scheduler_when_enabling(client):
    """Enabling the digest (or changing its webhook) without touching the
    time must still (re)start the scheduler — this was the 'never get
    digests' bug."""
    from app.routers import settings as settings_router  # noqa: E402

    calls = []
    old = settings_router._reschedule_digest
    settings_router.register_digest_rescheduler(lambda: calls.append(1))
    try:
        res = client.put(
            "/api/settings",
            json={
                "digest_enabled": True,
                "discord_webhook_url": "https://discord.com/api/webhooks/x",
                "digest_time": "08:00",
            },
        )
        assert res.status_code == 200, res.text
        assert calls, "saving digest settings did not re-arm the scheduler"
        assert res.json()["digest_timezone"] == ""
    finally:
        settings_router.register_digest_rescheduler(old)
        client.put(
            "/api/settings",
            json={"digest_enabled": False, "discord_webhook_url": ""},
        )


def test_save_rejects_bad_timezone(client):
    res = client.put("/api/settings", json={"digest_timezone": "Mars/Olympus"})
    assert res.status_code == 400
    assert "digest_timezone" in res.json()["detail"]


def test_scheduler_uses_configured_timezone():
    """The scheduled job fires in the configured zone, not server local."""
    from app.main import _maybe_start_digest_scheduler  # noqa: E402

    _set_settings_via_db(
        digest_enabled="true",
        discord_webhook_url="https://discord.com/api/webhooks/x",
        digest_time="08:00",
        digest_timezone="America/Chicago",
    )
    sched = None
    try:
        sched = _maybe_start_digest_scheduler()
        assert sched is not None
        job = sched.get_job("morning-digest")
        assert job is not None
        tz = job.trigger.timezone
        assert getattr(tz, "key", str(tz)) == "America/Chicago"
    finally:
        if sched is not None:
            sched.shutdown(wait=False)
        _set_settings_via_db(
            digest_enabled="false", discord_webhook_url="", digest_timezone=""
        )


def test_scheduler_not_started_when_disabled():
    from app.main import _maybe_start_digest_scheduler  # noqa: E402

    _set_settings_via_db(digest_enabled="false")
    assert _maybe_start_digest_scheduler() is None


def _unset_ai_briefing_setting():
    from sqlmodel import Session as _Session  # noqa: E402
    from sqlmodel import delete  # noqa: E402

    from app.database import engine as _engine  # noqa: E402
    from app.models import Setting  # noqa: E402

    with _Session(_engine) as s:
        s.exec(delete(Setting).where(Setting.key == "digest_ai_briefing"))
        s.commit()


def _mock_llm(monkeypatch, chat_impl):
    import app.llm as llm_mod  # noqa: E402

    monkeypatch.setattr(llm_mod, "get_config", lambda session: {"enabled": True})
    monkeypatch.setattr(llm_mod, "chat", chat_impl)


def test_ai_briefing_prepended(client, monkeypatch):
    """With the setting on and AI enabled, the preview gets a 🌤️ opener."""
    import app.llm as llm_mod  # noqa: E402

    _mock_llm(
        monkeypatch,
        lambda session, messages, json_mode=False, timeout=None: (
            "Good morning! Water the tomatoes first."
        ),
    )
    try:
        _set_settings_via_db(digest_ai_briefing="true")
        res = client.get("/api/digest/preview")
        assert res.status_code == 200
        msg = res.json()["message"]
        assert "🌤️ Good morning!" in msg
        # Data message still follows after the briefing.
        assert "Morning garden check" in msg
    finally:
        _set_settings_via_db(digest_ai_briefing="false")


def test_ai_briefing_fallback_on_error(client, monkeypatch):
    """A provider failure degrades to the data-only message — never an error."""
    import app.llm as llm_mod  # noqa: E402

    def boom(session, messages, json_mode=False, timeout=None):
        raise llm_mod.LLMError("boom")

    _mock_llm(monkeypatch, boom)
    try:
        _set_settings_via_db(digest_ai_briefing="true")
        res = client.get("/api/digest/preview")
        assert res.status_code == 200, res.text
        msg = res.json()["message"]
        assert "🌤️" not in msg
        assert "Morning garden check" in msg
    finally:
        _set_settings_via_db(digest_ai_briefing="false")


def test_ai_briefing_default_off(client, monkeypatch):
    """Setting unset (env fallback) means no briefing, even with AI up."""
    _mock_llm(
        monkeypatch,
        lambda session, messages, json_mode=False, timeout=None: "Should not appear.",
    )
    try:
        _unset_ai_briefing_setting()
        res = client.get("/api/digest/preview")
        assert res.status_code == 200
        msg = res.json()["message"]
        assert "🌤️" not in msg
        assert "Should not appear" not in msg
    finally:
        _set_settings_via_db(digest_ai_briefing="false")


def test_ai_briefing_setting_round_trip(client):
    """The new toggle saves via /api/settings and reads back."""
    try:
        res = client.put(
            "/api/settings",
            json={
                "digest_ai_briefing": True,
                "discord_webhook_url": "https://discord.com/api/webhooks/x",
            },
        )
        assert res.status_code == 200, res.text
        assert client.get("/api/settings").json()["digest_ai_briefing"] is True
        # It must not re-arm the scheduler (digest is time-based only).
        res = client.put("/api/settings", json={"digest_ai_briefing": False})
        assert res.status_code == 200
        assert client.get("/api/settings").json()["digest_ai_briefing"] is False
    finally:
        client.put(
            "/api/settings",
            json={"digest_ai_briefing": False, "discord_webhook_url": ""},
        )


def test_frost_alert_line(monkeypatch):
    """Frost in ~5 days warns with the date; far-future frost warns nothing."""
    from datetime import timedelta  # noqa: E402

    import app.frost as frost_mod  # noqa: E402
    from app.routers.digest import _frost_alert_line  # noqa: E402

    today = date.today()
    near = today + timedelta(days=5)
    monkeypatch.setattr(
        frost_mod,
        "resolve_frost",
        lambda session, which, today=None: (near, "zone", "6b"),
    )
    line = _frost_alert_line(None)
    assert line is not None
    assert "frost" in line.lower() and "5 days" in line
    assert near.strftime("%a %b %d") in line
    # Frost that already happened within the last week -> caution line.
    past = today - timedelta(days=3)
    monkeypatch.setattr(
        frost_mod,
        "resolve_frost",
        lambda session, which, today=None: (past, "exact", None),
    )
    line = _frost_alert_line(None)
    assert line is not None and "frost" in line.lower()
    # Far away -> nothing.
    far = today + timedelta(days=90)
    monkeypatch.setattr(
        frost_mod,
        "resolve_frost",
        lambda session, which, today=None: (far, "zone", "6b"),
    )
    assert _frost_alert_line(None) is None
    # No frost data -> nothing.
    monkeypatch.setattr(
        frost_mod,
        "resolve_frost",
        lambda session, which, today=None: (None, None, None),
    )
    assert _frost_alert_line(None) is None
