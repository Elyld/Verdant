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
        from sqlmodel import select as _select

        for pid in created:
            for model in (WateringLog, FertilizationLog, Harvest, ObservationLog):
                for row in s.exec(_select(model).where(model.plant_id == pid)).all():
                    s.delete(row)
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


# --- v2.44.0: tool-calling loop, richer context, OpenRouter model list ---

from datetime import date as _Date  # noqa: E402

from app import ai_tools as ai_tools_mod  # noqa: E402
from app.models import (  # noqa: E402
    Container,
    FertilizationLog,
    Harvest,
    ObservationLog,
    Planting,
    WateringLog,
)


def _log_care(session, plant_id):
    session.add(WateringLog(plant_id=plant_id, date="2026-09-20"))
    session.add(FertilizationLog(plant_id=plant_id, date="2026-09-15",
                                 fertilizer_name="Tomato-tone"))
    session.add(ObservationLog(plant_id=plant_id, plant_name="Cherokee Purple",
                               date="2026-09-18", notes="first flowers"))
    session.commit()


def _stub_chat_sequence(monkeypatch, contents):
    """Stub llm.chat with a sequence of responses (tool loop)."""
    calls = []
    queue = list(contents)

    def fake(session, messages, **kwargs):
        calls.append(messages)
        return queue.pop(0) if queue else json.dumps({"reply": "done"})

    monkeypatch.setattr(llm_mod, "chat", fake)
    return calls


def test_context_has_per_plant_care_history(garden):
    with SQLSession(engine) as s:
        _log_care(s, garden[0])
    with SQLSession(engine) as s:
        ctx = ai_context_mod.build_context(s)
    assert "Care history" in ctx
    assert "fed 2026-09-15 (Tomato-tone)" in ctx
    assert "watered 2026-09-20" in ctx
    assert "Genovese Basil" in ctx and "never fed" in ctx


def test_tool_loop_answers_from_tool_result(garden, monkeypatch):
    with SQLSession(engine) as s:
        _log_care(s, garden[0])
    calls = _stub_chat_sequence(monkeypatch, [
        json.dumps({"tool_calls": [
            {"name": "plant_care_history", "args": {"plant": "tomatoes"}}]}),
        json.dumps({"reply": "You last fed them 2026-09-15 with Tomato-tone."}),
    ])
    r = client.post("/api/ai/chat",
                    json={"message": "when did I last fertilize my tomatoes?",
                          "history": []})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "You last fed them 2026-09-15 with Tomato-tone."
    assert body["drafts"] == []
    assert len(calls) == 2  # tool call, then the final answer
    # The tool result made it back into the conversation.
    assert "Tomato-tone" in calls[1][-1]["content"]


def test_tool_loop_write_becomes_draft(garden, monkeypatch):
    calls = _stub_chat_sequence(monkeypatch, [
        json.dumps({"tool_calls": [
            {"name": "log_harvest",
             "args": {"plant": "Cherokee Purple", "quantity": 3}}]}),
        json.dumps({"reply": "Drafted your harvest — confirm to save."}),
    ])
    r = client.post("/api/ai/chat",
                    json={"message": "picked 3 tomatoes", "history": []})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["drafts"]) == 1
    d = body["drafts"][0]
    assert d["action"] == "harvest"
    assert d["plant_id"] == garden[0]
    assert d["amount"] == 3.0
    assert len(calls) == 2


def test_tool_loop_max_iters_still_replies(garden, monkeypatch):
    # A model that never stops calling tools still gets a final nudge.
    calls = _stub_chat_sequence(monkeypatch, [
        json.dumps({"tool_calls": [{"name": "reminders", "args": {}}]}),
        json.dumps({"tool_calls": [{"name": "reminders", "args": {}}]}),
        json.dumps({"tool_calls": [{"name": "reminders", "args": {}}]}),
        json.dumps({"reply": "Here's what I found."}),
    ])
    r = client.post("/api/ai/chat",
                    json={"message": "what's due?", "history": []})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "Here's what I found."
    assert len(calls) == ai_log.MAX_TOOL_ITERS + 1


def test_tool_loop_unknown_tool_reported(garden, monkeypatch):
    calls = _stub_chat_sequence(monkeypatch, [
        json.dumps({"tool_calls": [{"name": "teleport", "args": {}}]}),
        json.dumps({"reply": "Can't do that one."}),
    ])
    r = client.post("/api/ai/chat",
                    json={"message": "teleport me", "history": []})
    assert r.status_code == 200, r.text
    assert r.json()["drafts"] == []
    assert "unknown tool" in calls[1][-1]["content"]


def test_execute_read_plant_care_history(garden):
    with SQLSession(engine) as s:
        _log_care(s, garden[0])
    with SQLSession(engine) as s:
        res = ai_tools_mod.execute_read(
            s, "plant_care_history", {"plant": "cherokee purple"})
    assert res["last_watered"] == "2026-09-20"
    assert res["last_fertilized"]["product"] == "Tomato-tone"
    assert len(res["recent_notes"]) == 1


def test_execute_read_unknown_plant(garden):
    with SQLSession(engine) as s:
        res = ai_tools_mod.execute_read(s, "plant_care_history",
                                        {"plant": "moon carrots"})
    assert "error" in res


def test_build_write_draft_seed(garden):
    with SQLSession(engine) as s:
        d = ai_tools_mod.build_write_draft(
            s, "add_seed_packet",
            {"variety": "Brandywine", "species": "Tomato",
             "vendor": "Baker Creek", "year": "2024", "quantity": 25})
    assert d is not None
    assert d["action"] == "seed"
    assert d["plant_name"] == "Brandywine"
    assert d["seed_species"] == "Tomato"
    assert d["seed_vendor"] == "Baker Creek"
    assert d["seed_year"] == "2024"
    assert d["amount"] == 25.0


def test_build_write_draft_seed_needs_variety(garden):
    with SQLSession(engine) as s:
        assert ai_tools_mod.build_write_draft(
            s, "add_seed_packet", {"species": "Tomato"}) is None


def test_build_write_draft_plant_status(garden):
    with SQLSession(engine) as s:
        d = ai_tools_mod.build_write_draft(
            s, "update_plant",
            {"plant": "Genovese Basil", "status": "Done"})
    assert d is not None
    assert d["action"] == "plant_status"
    assert d["plant_id"] == garden[1]
    assert d["detail"] == "→ Done"


def test_build_write_draft_move_planting(garden):
    year = _Date.today().year
    with SQLSession(engine) as s:
        c1 = Container(name="Bed A", kind="raised bed", season_year=year)
        c2 = Container(name="Bed B", kind="raised bed", season_year=year)
        s.add(c1)
        s.add(c2)
        s.commit()
        s.refresh(c1)
        s.refresh(c2)
        s.add(Planting(container_id=c1.id, plant_id=garden[0],
                       season_year=year, slot=0))
        s.commit()
        d = ai_tools_mod.build_write_draft(
            s, "move_planting",
            {"plant": "Cherokee Purple", "to_container": "bed b"})
        assert d is not None
        assert d["action"] == "plant_move"
        assert d["to_container_id"] == c2.id
        assert d["planting_id"] is not None
        assert "Bed A → Bed B" in d["detail"]
        # cleanup
        for pl in s.exec(__import__("sqlmodel").select(Planting)).all():
            s.delete(pl)
        s.delete(c1)
        s.delete(c2)
        s.commit()


def test_build_write_draft_unknown_tool(garden):
    with SQLSession(engine) as s:
        assert ai_tools_mod.build_write_draft(s, "nope", {}) is None


def _fake_urlopen_factory(payload=None, exc=None):
    class _Resp:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        fake.calls += 1
        if exc is not None:
            raise exc
        return _Resp(json.dumps(payload).encode())

    fake.calls = 0
    return fake


def test_openrouter_models_lists_and_flags_free(monkeypatch):
    ai_log._OR_MODELS_CACHE.update(at=0.0, models=[])
    payload = {"data": [
        {"id": "openai/gpt-4o-mini", "name": "GPT-4o mini",
         "pricing": {"prompt": "0.00000015", "completion": "0.0000006"}},
        {"id": "meta-llama/llama-3.1-8b-instruct:free", "name": "Llama 3.1 8B",
         "pricing": {"prompt": "0", "completion": "0"}},
    ]}
    fake = _fake_urlopen_factory(payload=payload)
    monkeypatch.setattr("urllib.request.urlopen", fake)
    r = client.get("/api/ai/openrouter-models")
    assert r.status_code == 200
    models = r.json()["models"]
    assert len(models) == 2
    # free models sort first
    assert models[0]["id"].endswith(":free")
    assert models[0]["free"] is True
    assert models[1]["free"] is False
    # second call is served from cache — no second fetch
    r2 = client.get("/api/ai/openrouter-models")
    assert r2.status_code == 200
    assert fake.calls == 1
    ai_log._OR_MODELS_CACHE.update(at=0.0, models=[])


def test_openrouter_models_failure_returns_empty(monkeypatch):
    ai_log._OR_MODELS_CACHE.update(at=0.0, models=[])
    fake = _fake_urlopen_factory(exc=OSError("no network"))
    monkeypatch.setattr("urllib.request.urlopen", fake)
    r = client.get("/api/ai/openrouter-models")
    assert r.status_code == 200
    assert r.json() == {"models": []}
