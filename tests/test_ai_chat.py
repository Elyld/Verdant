"""In-app chat assistant (provider stubbed).

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="ai-chat-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402

from app import ai_context as ai_context_mod  # noqa: E402
from app import frost as frost_mod  # noqa: E402
from app import llm as llm_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Plant  # noqa: E402
from app.routers import ai_log  # noqa: E402

init_db()
client = TestClient(app)


def _settings(provider_on: bool = True, chat_on: bool = True) -> None:
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "local_ai_enabled", "true" if provider_on else "false")
        frost_mod.set_setting(s, "ai_provider", "ollama")
        frost_mod.set_setting(s, "ai_chat_enabled", "true" if chat_on else "false")
        s.commit()


@pytest.fixture
def garden():
    _settings(True, True)
    created = []
    with SQLSession(engine) as s:
        for name, species in (("Cherokee Purple", "Tomato"), ("Genovese Basil", "Basil")):
            p = Plant(variety_name=name, species_type=species, status="Growing")
            s.add(p)
            s.commit()
            s.refresh(p)
            created.append(p.id)
        s.commit()
    yield created
    _settings(False, True)
    with SQLSession(engine) as s:
        for pid in created:
            p = s.get(Plant, pid)
            if p:
                s.delete(p)
        s.commit()


@pytest.fixture(autouse=True)
def _defaults():
    _settings(False, True)
    yield
    _settings(False, True)


def _stub_chat(monkeypatch, content="", error=None):
    calls = []

    def fake(session, messages, **kwargs):
        calls.append(messages)
        if error is not None:
            raise error
        return content

    monkeypatch.setattr(llm_mod, "chat", fake)
    return calls


def test_chat_empty_message(garden):
    r = client.post("/api/ai/chat", json={"message": "   ", "history": []})
    assert r.status_code == 400


def test_chat_toggle_off(garden):
    _settings(True, False)
    r = client.post("/api/ai/chat", json={"message": "hi", "history": []})
    assert r.status_code == 400
    assert "chat assistant" in r.json()["detail"].lower()


def test_chat_provider_off(garden):
    _settings(False, True)
    r = client.post("/api/ai/chat", json={"message": "hi", "history": []})
    assert r.status_code == 400


def test_chat_reply_with_drafts(garden, monkeypatch):
    payload = {
        "reply": "Got it — drafted one watering.",
        "drafts": [{"action": "water", "plant": "Cherokee Purple",
                    "amount": None, "unit": None, "detail": None,
                    "notes": "morning water"}],
    }
    _stub_chat(monkeypatch, json.dumps(payload))
    r = client.post("/api/ai/chat", json={"message": "watered the tomatoes", "history": []})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["reply"] == "Got it — drafted one watering."
    assert len(body["drafts"]) == 1
    d = body["drafts"][0]
    assert d["action"] == "water"
    assert d["plant_id"] == garden[0]
    assert d["plant_name"] == "Cherokee Purple"


def test_chat_non_json_reply_has_no_drafts(garden, monkeypatch):
    _stub_chat(monkeypatch, "Just a plain answer, no JSON here.")
    r = client.post("/api/ai/chat", json={"message": "how are the tomatoes?", "history": []})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Just a plain answer, no JSON here."
    assert body["drafts"] == []


def test_chat_history_trimmed(garden, monkeypatch):
    calls = _stub_chat(monkeypatch, json.dumps({"reply": "ok", "drafts": []}))
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
               for i in range(30)]
    r = client.post("/api/ai/chat", json={"message": "latest", "history": history})
    assert r.status_code == 200
    sent = calls[0]
    # system + at most MAX_HISTORY turns + the new user message
    assert len(sent) <= ai_log.MAX_HISTORY + 2
    assert sent[0]["role"] == "system"
    assert sent[-1] == {"role": "user", "content": "latest"}
    assert sent[1]["content"] == "m22"  # oldest 8 kept, oldest-first


def test_chat_system_prompt_has_context(garden, monkeypatch):
    calls = _stub_chat(monkeypatch, json.dumps({"reply": "ok", "drafts": []}))
    client.post("/api/ai/chat", json={"message": "hi", "history": []})
    system = calls[0][0]["content"]
    assert "Cherokee Purple" in system
    assert "Genovese Basil" in system
    assert "JSON object" in system


def test_chat_llm_error_is_502(garden, monkeypatch):
    _stub_chat(monkeypatch, error=llm_mod.LLMError("boom", hint="check settings"))
    r = client.post("/api/ai/chat", json={"message": "hi", "history": []})
    assert r.status_code == 502
    assert "check settings" in r.json()["detail"]


def test_chat_status(garden, monkeypatch):
    _stub_chat(monkeypatch, "x")
    # stub llm.status via urlopen? simpler: status() with unreachable host
    r = client.get("/api/ai/chat-status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["provider"] == "ollama"
    assert "reachable" in body


def test_build_context_lists_plants(garden):
    with SQLSession(engine) as s:
        ctx = ai_context_mod.build_context(s)
    assert "Cherokee Purple" in ctx
    assert "Tomato" in ctx
    assert "Today is" in ctx


def test_build_context_empty_db():
    with SQLSession(engine) as s:
        ctx = ai_context_mod.build_context(s)
    assert isinstance(ctx, str) and "Today is" in ctx
