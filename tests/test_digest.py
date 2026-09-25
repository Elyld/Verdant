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
