"""Persistent agent self: identity files, threads, drafts (provider stubbed).

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="agent-self-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402
from sqlmodel import SQLModel, create_engine, select  # noqa: E402

from app import frost as frost_mod  # noqa: E402
from app import llm as llm_mod  # noqa: E402
from app.database import UPLOAD_DIR, _seed_agent_files, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AGENT_FILES,
    AgentConversation,
    AgentDraft,
    AgentFile,
    AgentMessage,
    Location,
    Plant,
    WateringLog,
)

assert UPLOAD_DIR  # engine binds the first-imported file's dirs

init_db()
client = TestClient(app)


def _settings(provider_on: bool = True, chat_on: bool = True) -> None:
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "local_ai_enabled", "true" if provider_on else "false")
        frost_mod.set_setting(s, "ai_provider", "ollama")
        frost_mod.set_setting(s, "ai_chat_enabled", "true" if chat_on else "false")
        s.commit()


@pytest.fixture(autouse=True)
def _defaults():
    _settings(True, True)
    yield
    _settings(False, True)


@pytest.fixture
def garden():
    created = []
    with SQLSession(engine) as s:
        loc = Location(name="Test Bed")
        s.add(loc)
        s.commit()
        s.refresh(loc)
        p = Plant(variety_name="Cherokee Purple", species_type="Tomato",
                  status="Growing", location_id=loc.id)
        s.add(p)
        s.commit()
        s.refresh(p)
        created.append((p.id, loc.id))
        s.commit()
    yield created[0][0]
    _settings(False, True)
    with SQLSession(engine) as s:
        pid, lid = created[0]
        for row in s.exec(select(WateringLog).where(WateringLog.plant_id == pid)).all():
            s.delete(row)
        for row in s.exec(select(AgentMessage)).all():
            s.delete(row)
        for row in s.exec(select(AgentDraft)).all():
            s.delete(row)
        for row in s.exec(select(AgentConversation)).all():
            s.delete(row)
        p = s.get(Plant, pid)
        if p:
            s.delete(p)
        loc = s.get(Location, lid)
        if loc:
            s.delete(loc)
        s.commit()


@pytest.fixture
def files_snapshot():
    """Restore agent file contents after each test (PUTs persist)."""
    with SQLSession(engine) as s:
        snap = {f.name: f.content for f in s.exec(select(AgentFile)).all()}
    yield
    with SQLSession(engine) as s:
        for name, content in snap.items():
            row = s.get(AgentFile, name)
            if row is not None:
                row.content = content
                s.add(row)
        s.commit()


def _stub_chat(monkeypatch, *contents, error=None):
    calls = []
    queue = list(contents)

    def fake(session, messages, **kwargs):
        calls.append(messages)
        if error is not None:
            raise error
        return queue.pop(0) if queue else json.dumps({"reply": "done"})

    monkeypatch.setattr(llm_mod, "chat", fake)
    return calls


# --------------------------------------------------------------------------- #
# Identity files
# --------------------------------------------------------------------------- #

def test_files_seeded_with_defaults():
    r = client.get("/api/agent/files")
    assert r.status_code == 200
    files = {f["name"]: f["content"] for f in r.json()["files"]}
    assert set(files) == set(AGENT_FILES)
    assert "Verdant" in files["persona"]


def test_seed_never_clobbers_edits(files_snapshot):
    r = client.put("/api/agent/files/memory", json={"content": "gardener's own words"})
    assert r.status_code == 200
    _seed_agent_files()  # re-seed must not overwrite
    r = client.get("/api/agent/files")
    files = {f["name"]: f["content"] for f in r.json()["files"]}
    assert files["memory"] == "gardener's own words"


def test_put_file_unknown_name_404():
    r = client.put("/api/agent/files/nonexistent", json={"content": "x"})
    assert r.status_code == 404


def test_identity_files_reach_the_prompt(garden, monkeypatch, files_snapshot):
    marker = "MARKER-PERSONA-77Z"
    client.put("/api/agent/files/persona", json={"content": marker})
    calls = _stub_chat(monkeypatch, json.dumps({"reply": "hi"}))
    r = client.post("/api/agent/conversations", json={})
    conv_id = r.json()["id"]
    r = client.post(f"/api/agent/conversations/{conv_id}/messages",
                    json={"message": "hello"})
    assert r.status_code == 200, r.text
    system = calls[0][0]["content"]
    assert calls[0][0]["role"] == "system"
    assert marker in system
    assert "operating_notes" in system.lower() or "learned" in system.lower()


# --------------------------------------------------------------------------- #
# Conversations
# --------------------------------------------------------------------------- #

def test_conversation_round_trip(garden, monkeypatch):
    _stub_chat(monkeypatch, json.dumps({"reply": "looking good"}))
    r = client.post("/api/agent/conversations", json={"title": ""})
    assert r.status_code == 201
    conv_id = r.json()["id"]

    r = client.post(f"/api/agent/conversations/{conv_id}/messages",
                    json={"message": "how are the tomatoes?"})
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "looking good"

    # "Refresh": brand-new HTTP requests read both sides back from the DB.
    r = client.get(f"/api/agent/conversations/{conv_id}/messages")
    roles = [(m["role"], m["content"]) for m in r.json()["messages"]]
    assert roles == [("user", "how are the tomatoes?"), ("assistant", "looking good")]

    r = client.get("/api/agent/conversations")
    convs = r.json()["conversations"]
    assert any(c["id"] == conv_id and c["message_count"] == 2 for c in convs)
    # title auto-derived from the first message
    assert any(c["id"] == conv_id and "tomatoes" in c["title"] for c in convs)


def test_history_loaded_from_db(garden, monkeypatch):
    _stub_chat(monkeypatch,
               json.dumps({"reply": "first answer"}),
               json.dumps({"reply": "second answer"}))
    conv_id = client.post("/api/agent/conversations", json={}).json()["id"]
    client.post(f"/api/agent/conversations/{conv_id}/messages",
                json={"message": "first question"})
    calls = _stub_chat(monkeypatch, json.dumps({"reply": "second answer"}))
    client.post(f"/api/agent/conversations/{conv_id}/messages",
                json={"message": "follow-up"})
    contents = [m["content"] for m in calls[0]]
    assert any("first question" in c for c in contents)
    assert any("first answer" in c for c in contents)


def test_conversation_requires_chat_enabled(garden):
    _settings(True, False)
    conv_id = client.post("/api/agent/conversations", json={}).json()["id"]
    r = client.post(f"/api/agent/conversations/{conv_id}/messages",
                    json={"message": "hi"})
    assert r.status_code == 400


def test_delete_conversation_cascades(garden, monkeypatch):
    _stub_chat(monkeypatch, json.dumps({"reply": "ok"}))
    conv_id = client.post("/api/agent/conversations", json={}).json()["id"]
    client.post(f"/api/agent/conversations/{conv_id}/messages",
                json={"message": "hi"})
    r = client.delete(f"/api/agent/conversations/{conv_id}")
    assert r.status_code == 200
    with SQLSession(engine) as s:
        assert s.get(AgentConversation, conv_id) is None
        assert s.exec(select(AgentMessage)
                      .where(AgentMessage.conversation_id == conv_id)).all() == []


# --------------------------------------------------------------------------- #
# Drafts
# --------------------------------------------------------------------------- #

def _water_draft_via_chat(monkeypatch):
    """Stub the model into calling log_watering, then send one message."""
    _stub_chat(
        monkeypatch,
        json.dumps({"tool_calls": [
            {"name": "log_watering",
             "args": {"plant": "Cherokee Purple", "notes": "morning"}}]}),
        json.dumps({"reply": "Drafted — confirm and I'll save it."}),
    )
    conv_id = client.post("/api/agent/conversations", json={}).json()["id"]
    r = client.post(f"/api/agent/conversations/{conv_id}/messages",
                    json={"message": "watered the tomatoes"})
    assert r.status_code == 200, r.text
    return conv_id, r.json()["drafts"]


def test_draft_persists_across_refresh(garden, monkeypatch):
    conv_id, drafts = _water_draft_via_chat(monkeypatch)
    assert len(drafts) == 1
    assert drafts[0]["kind"] == "water"
    # "Refresh": the draft is still there on a fresh read.
    r = client.get(f"/api/agent/drafts?conversation_id={conv_id}")
    assert len(r.json()["drafts"]) == 1
    # Nothing was written silently.
    with SQLSession(engine) as s:
        assert s.exec(select(WateringLog)).all() == []


def test_confirm_draft_writes_and_clears(garden, monkeypatch):
    conv_id, drafts = _water_draft_via_chat(monkeypatch)
    draft_id = drafts[0]["id"]
    r = client.post(f"/api/agent/drafts/{draft_id}/confirm")
    assert r.status_code == 200, r.text
    assert "Cherokee Purple" in r.json()["summary"]
    with SQLSession(engine) as s:
        logs = s.exec(select(WateringLog)).all()
        assert len(logs) == 1
        assert logs[0].plant_id is not None
        assert s.get(AgentDraft, draft_id) is None
    r = client.get(f"/api/agent/drafts?conversation_id={conv_id}")
    assert r.json()["drafts"] == []


def test_discard_draft_writes_nothing(garden, monkeypatch):
    conv_id, drafts = _water_draft_via_chat(monkeypatch)
    draft_id = drafts[0]["id"]
    r = client.post(f"/api/agent/drafts/{draft_id}/discard")
    assert r.status_code == 200
    with SQLSession(engine) as s:
        assert s.exec(select(WateringLog)).all() == []
        assert s.get(AgentDraft, draft_id) is None


def test_confirm_unknown_draft_404():
    r = client.post("/api/agent/drafts/999999/confirm")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# propose_memory_write — drafts, never silent writes
# --------------------------------------------------------------------------- #

def test_memory_write_tool_creates_draft_not_a_write(garden, monkeypatch,
                                                     files_snapshot):
    _stub_chat(
        monkeypatch,
        json.dumps({"tool_calls": [
            {"name": "propose_memory_write",
             "args": {"file": "memory",
                     "addition": "Loves Cherokee Purple tomatoes"}}]}),
        json.dumps({"reply": "Confirm the draft and I'll remember it."}),
    )
    conv_id = client.post("/api/agent/conversations", json={}).json()["id"]
    r = client.post(f"/api/agent/conversations/{conv_id}/messages",
                    json={"message": "remember I love Cherokee Purple tomatoes"})
    assert r.status_code == 200, r.text
    drafts = r.json()["drafts"]
    assert len(drafts) == 1
    assert drafts[0]["kind"] == "memory_write"
    assert drafts[0]["payload"]["memory_file"] == "memory"
    # The file is untouched until the gardener confirms.
    r = client.get("/api/agent/files")
    memory = next(f for f in r.json()["files"] if f["name"] == "memory")
    assert "Cherokee Purple" not in memory["content"]

    # Confirm → the line lands in the file.
    r = client.post(f"/api/agent/drafts/{drafts[0]['id']}/confirm")
    assert r.status_code == 200
    r = client.get("/api/agent/files")
    memory = next(f for f in r.json()["files"] if f["name"] == "memory")
    assert "Loves Cherokee Purple tomatoes" in memory["content"]


def test_memory_write_bad_file_is_rejected(garden, monkeypatch):
    _stub_chat(
        monkeypatch,
        json.dumps({"tool_calls": [
            {"name": "propose_memory_write",
             "args": {"file": "diary", "addition": "junk"}}]}),
        json.dumps({"reply": "ok"}),
    )
    conv_id = client.post("/api/agent/conversations", json={}).json()["id"]
    r = client.post(f"/api/agent/conversations/{conv_id}/messages",
                    json={"message": "remember this"})
    assert r.status_code == 200
    assert r.json()["drafts"] == []


def test_memory_write_in_tool_catalogue():
    from app import ai_tools as ai_tools_mod

    names = [t["name"] for t in ai_tools_mod.TOOLS]
    assert "propose_memory_write" in names
    assert "propose_memory_write" not in ai_tools_mod.READ_TOOLS


# --------------------------------------------------------------------------- #
# Upgrade: an old DB gains the agent tables + seeded files, data intact
# --------------------------------------------------------------------------- #

def test_upgrade_creates_agent_tables_and_seeds(tmp_path):
    db = str(tmp_path / "garden.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE plants (id INTEGER PRIMARY KEY, variety_name TEXT)")
    con.execute("INSERT INTO plants (variety_name) VALUES ('Old Tomato')")
    con.commit()
    con.close()

    from app.database import _apply_column_migrations

    eng = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(eng)
    _apply_column_migrations(eng)
    _seed_agent_files(eng)

    con = sqlite3.connect(db)
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"agent_files", "agent_conversations",
                "agent_messages", "agent_drafts"} <= tables
        assert con.execute(
            "SELECT variety_name FROM plants").fetchone() == ("Old Tomato",)
        assert con.execute("SELECT COUNT(*) FROM agent_files").fetchone()[0] == 3
    finally:
        con.close()
