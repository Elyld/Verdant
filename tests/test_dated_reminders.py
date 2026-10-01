"""Dated reminders set via the AI chat (v2.50.0).

Covers: set_reminder draft creation + date validation, the
/api/user-reminders CRUD endpoints, upcoming_reminders ordering
(overdue first), the chat context block, and the digest 🔔 section.

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import os
import tempfile
import time
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="dated-reminders-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession, select  # noqa: E402

from app import ai_context as ai_context_mod  # noqa: E402
from app import ai_tools as ai_tools_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import UserReminder  # noqa: E402
from app.routers import digest as digest_mod  # noqa: E402

init_db()
client = TestClient(app)

UID = str(int(time.time() * 1000) % 100000)


def _title(tag: str) -> str:
    return f"TEST-{UID}-{tag}"


@pytest.fixture
def reminders():
    created = []

    def _make(title, due_date, notes=None, done=False, via_db=False):
        if via_db:
            with SQLSession(engine) as s:
                r = UserReminder(title=title, due_date=due_date,
                                 notes=notes, done=done)
                s.add(r)
                s.commit()
                s.refresh(r)
                created.append(r.id)
                return r.id
        resp = client.post("/api/user-reminders",
                           json={"title": title, "due_date": due_date,
                                 "notes": notes})
        assert resp.status_code == 200, resp.text
        rid = resp.json()["reminder"]["id"]
        created.append(rid)
        return rid

    yield _make
    with SQLSession(engine) as s:
        for rid in created:
            r = s.get(UserReminder, rid)
            if r:
                s.delete(r)
        s.commit()


# --- set_reminder draft creation -------------------------------------------

def test_set_reminder_draft_with_session():
    future = (Date.today() + timedelta(days=9)).isoformat()
    with SQLSession(engine) as s:
        d = ai_tools_mod.build_write_draft(
            s, "set_reminder",
            {"title": "plant carrots", "due_date": future})
    assert d is not None
    assert d["action"] == "reminder"
    assert d["reminder_title"] == "plant carrots"
    assert d["reminder_due"] == future
    assert "set_reminder" in ai_tools_mod.WRITE_TOOL_ACTIONS
    assert "upcoming_reminders" in ai_tools_mod.READ_TOOLS


def test_set_reminder_rejects_bad_and_past_dates():
    with SQLSession(engine) as s:
        assert ai_tools_mod.build_write_draft(
            s, "set_reminder",
            {"title": "x", "due_date": "not-a-date"}) is None
        assert ai_tools_mod.build_write_draft(
            s, "set_reminder",
            {"title": "x", "due_date": "2026-13-45"}) is None
        past = (Date.today() - timedelta(days=1)).isoformat()
        assert ai_tools_mod.build_write_draft(
            s, "set_reminder",
            {"title": "x", "due_date": past}) is None
        assert ai_tools_mod.build_write_draft(
            s, "set_reminder",
            {"title": "  ", "due_date": (Date.today() + timedelta(days=1)).isoformat()}) is None
        # today is fine
        d = ai_tools_mod.build_write_draft(
            s, "set_reminder",
            {"title": "x", "due_date": Date.today().isoformat()})
        assert d is not None and d["reminder_due"] == Date.today().isoformat()


# --- /api/user-reminders CRUD ----------------------------------------------

def test_endpoint_create_list_and_validation(reminders):
    future = (Date.today() + timedelta(days=5)).isoformat()
    rid = reminders(_title("carrots"), future, notes="raised bed")
    resp = client.get("/api/user-reminders")
    assert resp.status_code == 200
    rows = resp.json()["reminders"]
    assert any(r["id"] == rid and r["title"] == _title("carrots") for r in rows)

    # bad format rejected
    bad = client.post("/api/user-reminders",
                      json={"title": "x", "due_date": "tomorrow"})
    assert bad.status_code == 400
    # past date rejected
    past = client.post("/api/user-reminders",
                       json={"title": "x",
                             "due_date": (Date.today() - timedelta(days=2)).isoformat()})
    assert past.status_code == 400
    # blank title rejected
    blank = client.post("/api/user-reminders",
                        json={"title": "  ", "due_date": future})
    assert blank.status_code == 400


def test_endpoint_done_and_delete(reminders):
    future = (Date.today() + timedelta(days=5)).isoformat()
    rid = reminders(_title("done-me"), future)
    resp = client.patch(f"/api/user-reminders/{rid}", json={"done": True})
    assert resp.status_code == 200
    assert resp.json()["reminder"]["done"] is True
    # done reminders leave the default (pending) list
    rows = client.get("/api/user-reminders").json()["reminders"]
    assert not any(r["id"] == rid for r in rows)
    # ...but show up with all=true
    rows = client.get("/api/user-reminders", params={"all": "true"}).json()["reminders"]
    assert any(r["id"] == rid for r in rows)
    assert client.delete(f"/api/user-reminders/{rid}").status_code == 200
    assert client.delete(f"/api/user-reminders/{rid}").status_code == 404


# --- upcoming_reminders tool: overdue first --------------------------------

def test_upcoming_reminders_orders_overdue_first(reminders):
    overdue_date = (Date.today() - timedelta(days=3)).isoformat()
    future = (Date.today() + timedelta(days=6)).isoformat()
    reminders(_title("overdue-item"), overdue_date, via_db=True)
    reminders(_title("future-item"), future)
    with SQLSession(engine) as s:
        out = ai_tools_mod.execute_read(s, "upcoming_reminders", {})
    rows = out["reminders"]
    mine = [r for r in rows if r["title"].startswith(f"TEST-{UID}-")]
    assert len(mine) == 2
    assert mine[0]["title"] == _title("overdue-item")
    assert mine[0]["status"] == "overdue"
    assert mine[1]["title"] == _title("future-item")


# --- context block ----------------------------------------------------------

def test_context_block_includes_due_reminder(reminders):
    reminders(_title("ctx-carrots"), Date.today().isoformat())
    with SQLSession(engine) as s:
        ctx = ai_context_mod.build_context(s)
    assert _title("ctx-carrots") in ctx
    assert "due today" in ctx


def test_context_block_skips_far_future(reminders):
    far = (Date.today() + timedelta(days=60)).isoformat()
    reminders(_title("ctx-far"), far)
    with SQLSession(engine) as s:
        ctx = ai_context_mod.build_context(s)
    assert _title("ctx-far") not in ctx


# --- digest 🔔 section -------------------------------------------------------

def test_digest_includes_reminders_section(reminders):
    overdue_date = (Date.today() - timedelta(days=2)).isoformat()
    reminders(_title("digest-overdue"), overdue_date, via_db=True)
    with SQLSession(engine) as s:
        urems = digest_mod._pending_user_reminders(s)
    mine = [r for r in urems if r.title.startswith(f"TEST-{UID}-")]
    msg = digest_mod.build_digest_message([], user_reminders=mine)
    assert "🔔" in msg
    assert _title("digest-overdue") in msg
    assert "overdue" in msg


def test_digest_all_clear_ignores_done_but_not_pending(reminders):
    future = (Date.today() + timedelta(days=4)).isoformat()
    rid = reminders(_title("digest-pending"), future)
    with SQLSession(engine) as s:
        urems = digest_mod._pending_user_reminders(s)
    mine = [r for r in urems if r.title.startswith(f"TEST-{UID}-")]
    msg = digest_mod.build_digest_message([], user_reminders=mine)
    assert "All clear" not in msg
    client.patch(f"/api/user-reminders/{rid}", json={"done": True})
    with SQLSession(engine) as s:
        urems = digest_mod._pending_user_reminders(s)
    mine = [r for r in urems if r.title.startswith(f"TEST-{UID}-")]
    msg = digest_mod.build_digest_message([], user_reminders=mine)
    assert "All clear" in msg
