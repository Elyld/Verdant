"""Vision support ("eyes") + the AI voice-log endpoint (provider stubbed).

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="ai-vision-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402

import app.llm as llm_mod  # noqa: E402
from app import frost as frost_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Plant  # noqa: E402
from app.routers import ai_log  # noqa: E402

init_db()
client = TestClient(app)


def _settings(on: bool = True) -> None:
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "local_ai_enabled", "true" if on else "false")
        frost_mod.set_setting(s, "ai_provider", "ollama")
        frost_mod.set_setting(s, "ai_chat_enabled", "true")
        s.commit()


@pytest.fixture(autouse=True)
def _defaults():
    _settings(True)
    yield
    _settings(False)


def _stub_chat(monkeypatch, content=""):
    calls = []

    def fake(session, messages, **kwargs):
        calls.append((messages, kwargs))
        return content

    monkeypatch.setattr(ai_log.llm_mod, "chat", fake)
    return calls


# --- llm.py provider image plumbing -----------------------------------------

def test_openrouter_image_parts(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout, headers=None):
        captured["url"] = url
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm_mod, "_post_json", fake_post_json)
    original = [{"role": "user", "content": "hi"}]
    out = llm_mod._openrouter_chat(
        "k", "m", original, False, 10,
        images=["data:image/jpeg;base64,AAA"])
    assert out == "ok"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    sent = captured["payload"]["messages"]
    content = sent[0]["content"]
    assert content[0] == {"type": "text", "text": "hi"}
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,AAA"},
    }
    # caller-owned list untouched
    assert original == [{"role": "user", "content": "hi"}]


def test_openrouter_no_images_keeps_string_content(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout, headers=None):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm_mod, "_post_json", fake_post_json)
    llm_mod._openrouter_chat("k", "m", [{"role": "user", "content": "hi"}],
                             False, 10)
    assert captured["payload"]["messages"][0]["content"] == "hi"


def test_openrouter_images_ignored_when_last_is_not_user(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout, headers=None):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm_mod, "_post_json", fake_post_json)
    msgs = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"}]
    llm_mod._openrouter_chat("k", "m", msgs, False, 10,
                             images=["data:image/jpeg;base64,AAA"])
    assert captured["payload"]["messages"] == msgs


def test_ollama_image_parts(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout, headers=None):
        captured["payload"] = payload
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(llm_mod, "_post_json", fake_post_json)
    original = [{"role": "user", "content": "hi"}]
    out = llm_mod._ollama_chat(
        "http://x:11434", "m", original, False, 10,
        images=["data:image/png;base64,BBB", "https://example.com/x.jpg"])
    assert out == "ok"
    sent = captured["payload"]["messages"]
    assert sent[-1]["images"] == ["BBB"]  # https URL skipped
    # caller's original list was not mutated
    assert original == [{"role": "user", "content": "hi"}]
    assert "images" not in original[0]


def test_ollama_blank_images_ignored(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout, headers=None):
        captured["payload"] = payload
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(llm_mod, "_post_json", fake_post_json)
    llm_mod._ollama_chat("http://x:11434", "m",
                         [{"role": "user", "content": "hi"}],
                         False, 10, images=["", "   "])
    assert "images" not in captured["payload"]["messages"][-1]


# --- /api/ai/chat with an attached image ------------------------------------

def test_chat_with_image_forwards_to_llm(monkeypatch):
    calls = _stub_chat(monkeypatch, '{"reply": "I see aphids on the leaves."}')
    monkeypatch.setattr(ai_log.llm_mod, "model_supports_vision", lambda session: True)
    r = client.post("/api/ai/chat", json={
        "message": "what's on my leaves?",
        "image": "data:image/jpeg;base64,AAA",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "aphids" in body["reply"].lower()
    messages, kwargs = calls[0]
    assert kwargs["images"] == ["data:image/jpeg;base64,AAA"]
    # the vision sentence lands in the system prompt
    assert "you CAN see it" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "what's on my leaves?"}


def test_chat_with_image_text_only_model_is_honest(monkeypatch):
    calls = _stub_chat(monkeypatch, '{"reply": "I cannot see images."}')
    monkeypatch.setattr(ai_log.llm_mod, "model_supports_vision", lambda session: False)
    r = client.post("/api/ai/chat", json={
        "message": "what's on my leaves?",
        "image": "data:image/jpeg;base64,AAA",
    })
    assert r.status_code == 200, r.text
    messages, _ = calls[0]
    system = messages[0]["content"]
    assert "you CAN see it" not in system
    assert "cannot see images" in system
    assert "never" in system and "guess" in system  # no hallucinating the photo


# --- model_supports_vision ---------------------------------------------------

def _set_model(monkeypatch, provider, model):
    llm_mod._VISION_CACHE.clear()
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "ai_provider", provider)
        if provider == "ollama":
            frost_mod.set_setting(s, "local_ai_model", model)
        else:
            frost_mod.set_setting(s, "openrouter_model", model)
        s.commit()


def _vision_with(monkeypatch):
    with SQLSession(engine) as s:
        return llm_mod.model_supports_vision(s)


def test_vision_ollama_reports_vision(monkeypatch):
    def fake_post_json(url, payload, timeout, headers=None):
        assert url.endswith("/api/show")
        return {"capabilities": ["completion", "vision"]}
    monkeypatch.setattr(llm_mod, "_post_json", fake_post_json)
    _set_model(monkeypatch, "ollama", "llava:latest")
    assert _vision_with(monkeypatch) is True


def test_vision_ollama_text_only(monkeypatch):
    def fake_post_json(url, payload, timeout, headers=None):
        return {"capabilities": ["completion"]}
    monkeypatch.setattr(llm_mod, "_post_json", fake_post_json)
    _set_model(monkeypatch, "ollama", "qwen3:4b")
    assert _vision_with(monkeypatch) is False


def test_vision_ollama_unreachable_is_conservative(monkeypatch):
    def boom(url, payload, timeout, headers=None):
        raise llm_mod.LLMError("nope")
    monkeypatch.setattr(llm_mod, "_post_json", boom)
    _set_model(monkeypatch, "ollama", "llava:latest")
    assert _vision_with(monkeypatch) is False


def test_vision_openrouter_image_modality(monkeypatch):
    def fake_get_json(url, timeout, headers=None):
        return {"data": [
            {"id": "openai/gpt-4o-mini",
             "architecture": {"input_modalities": ["text", "image"]}},
            {"id": "meta-llama/llama-3-8b",
             "architecture": {"input_modalities": ["text"]}},
        ]}
    monkeypatch.setattr(llm_mod, "_get_json", fake_get_json)
    _set_model(monkeypatch, "openrouter", "openai/gpt-4o-mini")
    assert _vision_with(monkeypatch) is True
    _set_model(monkeypatch, "openrouter", "meta-llama/llama-3-8b")
    assert _vision_with(monkeypatch) is False
    _set_model(monkeypatch, "openrouter", "unknown/model-xyz")
    assert _vision_with(monkeypatch) is False


def test_vision_result_is_cached(monkeypatch):
    hits = []

    def fake_post_json(url, payload, timeout, headers=None):
        hits.append(url)
        return {"capabilities": ["vision"]}
    monkeypatch.setattr(llm_mod, "_post_json", fake_post_json)
    _set_model(monkeypatch, "ollama", "llava:latest")
    assert _vision_with(monkeypatch) is True
    assert _vision_with(monkeypatch) is True
    assert len(hits) == 1  # second call served from cache


def test_chat_rejects_bad_image(monkeypatch):
    _stub_chat(monkeypatch, '{"reply": "ok"}')
    r = client.post("/api/ai/chat", json={"message": "hi", "image": "not-a-url"})
    assert r.status_code == 400


def test_chat_rejects_oversized_image(monkeypatch):
    _stub_chat(monkeypatch, '{"reply": "ok"}')
    r = client.post("/api/ai/chat", json={
        "message": "hi",
        "image": "data:image/jpeg;base64," + "A" * (ai_log.MAX_IMAGE_LEN + 1),
    })
    assert r.status_code == 400


def test_chat_without_image_passes_none(monkeypatch):
    calls = _stub_chat(monkeypatch, '{"reply": "ok"}')
    r = client.post("/api/ai/chat", json={"message": "hi"})
    assert r.status_code == 200, r.text
    _, kwargs = calls[0]
    assert kwargs["images"] is None


# --- /api/ai/voice-log ------------------------------------------------------

def test_voice_log_returns_drafts(monkeypatch):
    pid = None
    with SQLSession(engine) as s:
        p = Plant(variety_name="Cherokee Purple", species_type="Tomato",
                  status="Growing")
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
    try:
        _stub_chat(monkeypatch, (
            '[{"action":"water","plant":"Cherokee Purple","amount":null,'
            '"unit":null,"detail":null,"notes":"evening watering"}]'))
        r = client.post("/api/ai/voice-log",
                        json={"transcript": "watered the tomatoes this evening"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert len(body["drafts"]) == 1
        d = body["drafts"][0]
        assert d["action"] == "water"
        assert d["plant_name"] == "Cherokee Purple"
        assert d["plant_id"] == pid
    finally:
        with SQLSession(engine) as s:
            p = s.get(Plant, pid)
            if p:
                s.delete(p)
                s.commit()


def test_voice_log_empty_rejected(monkeypatch):
    _stub_chat(monkeypatch, "[]")
    r = client.post("/api/ai/voice-log", json={"transcript": "   "})
    assert r.status_code == 400


def test_voice_log_ai_off_rejected(monkeypatch):
    _stub_chat(monkeypatch, "[]")
    _settings(False)
    r = client.post("/api/ai/voice-log", json={"transcript": "watered tomatoes"})
    assert r.status_code == 400


def test_interpret_still_works_after_refactor(monkeypatch):
    # The interpret → _interpret_text refactor must not change behavior.
    _stub_chat(monkeypatch, (
        '[{"action":"harvest","plant":null,"amount":3,"unit":null,'
        '"detail":null,"notes":"picked peppers"}]'))
    r = client.post("/api/ai/interpret", json={"text": "picked 3 peppers"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["drafts"]) == 1
    assert body["drafts"][0]["action"] == "harvest"
    assert body["drafts"][0]["amount"] == 3.0
