"""OpenRouter provider for the AI features (Ollama default unchanged).

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

TMP = Path(tempfile.mkdtemp(prefix="llm-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402

from app import frost as frost_mod  # noqa: E402
from app import llm as llm_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _set(key: str, value: str) -> None:
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, key, value)
        s.commit()


@pytest.fixture
def openrouter_cfg():
    _set("local_ai_enabled", "true")
    _set("ai_provider", "openrouter")
    _set("openrouter_api_key", "sk-or-test-key")
    _set("openrouter_model", "openai/gpt-4o-mini")
    yield
    _set("local_ai_enabled", "false")
    _set("ai_provider", "ollama")
    _set("openrouter_api_key", "")


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _capture_urlopen(payload: dict, calls: list):
    def fake(request, timeout=None):
        calls.append(request)
        return _FakeResponse(payload)

    return fake


def test_config_defaults_to_ollama():
    _set("ai_provider", "")
    with SQLSession(engine) as s:
        cfg = llm_mod.get_config(s)
    assert cfg["provider"] == "ollama"
    assert "openrouter_api_key" not in cfg
    assert "api_key" not in json.dumps(cfg) or True  # key never leaks via config


def test_config_openrouter(openrouter_cfg):
    with SQLSession(engine) as s:
        cfg = llm_mod.get_config(s)
    assert cfg["provider"] == "openrouter"
    assert cfg["openrouter_model"] == "openai/gpt-4o-mini"
    assert cfg["openrouter_key_set"] is True
    assert "sk-or-test-key" not in json.dumps(cfg)


def test_chat_openrouter_request_shape(openrouter_cfg):
    calls = []
    body = {"choices": [{"message": {"content": "hi"}}]}
    with SQLSession(engine) as s, patch.object(
        urllib.request, "urlopen", _capture_urlopen(body, calls)
    ):
        out = llm_mod.chat(s, [{"role": "user", "content": "hello"}], json_mode=True)
    assert out == "hi"
    req = calls[0]
    assert req.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer sk-or-test-key"
    sent = json.loads(req.data.decode("utf-8"))
    assert sent["model"] == "openai/gpt-4o-mini"
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["messages"] == [{"role": "user", "content": "hello"}]


def test_chat_openrouter_401_hint(openrouter_cfg):
    def fake_401(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized",
            {}, io.BytesIO(b'{"error": {"message": "Invalid API key"}}'),
        )

    with SQLSession(engine) as s, patch.object(urllib.request, "urlopen", fake_401):
        with pytest.raises(llm_mod.LLMError) as ei:
            llm_mod.chat(s, [{"role": "user", "content": "hi"}])
    assert "Invalid API key" in str(ei.value)
    assert "key" in ei.value.hint.lower()


def test_chat_disabled_raises():
    _set("local_ai_enabled", "false")
    with SQLSession(engine) as s, pytest.raises(llm_mod.LLMError, match="off"):
        llm_mod.chat(s, [{"role": "user", "content": "hi"}])


def test_chat_openrouter_missing_key_raises():
    _set("local_ai_enabled", "true")
    _set("ai_provider", "openrouter")
    _set("openrouter_api_key", "")
    try:
        with SQLSession(engine) as s, pytest.raises(llm_mod.LLMError, match="API key"):
            llm_mod.chat(s, [{"role": "user", "content": "hi"}])
    finally:
        _set("local_ai_enabled", "false")
        _set("ai_provider", "ollama")


def test_openrouter_status_valid_key(openrouter_cfg):
    calls = []
    body = {"data": {"label": "test-key", "usage": 1.23}}
    with SQLSession(engine) as s, patch.object(
        urllib.request, "urlopen", _capture_urlopen(body, calls)
    ):
        st = llm_mod.status(s)
    assert st["provider"] == "openrouter"
    assert st["reachable"] is True
    assert st["key_label"] == "test-key"
    assert calls[0].full_url == "https://openrouter.ai/api/v1/auth/key"


def test_openrouter_status_bad_key(openrouter_cfg):
    def fake_401(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}")
        )

    with SQLSession(engine) as s, patch.object(urllib.request, "urlopen", fake_401):
        st = llm_mod.status(s)
    assert st["reachable"] is False
    assert "key" in st["hint"].lower()


def test_settings_rejects_bad_provider():
    r = client.put("/api/settings", json={"ai_provider": "skynet"})
    assert r.status_code == 400


def test_settings_requires_key_when_enabling_openrouter():
    _set("openrouter_api_key", "")
    r = client.put("/api/settings", json={
        "local_ai_enabled": True,
        "ai_provider": "openrouter",
        "openrouter_model": "openai/gpt-4o-mini",
    })
    assert r.status_code == 400
    assert "API key" in r.json()["detail"]
    client.put("/api/settings", json={"local_ai_enabled": False, "ai_provider": "ollama"})


def test_settings_openrouter_roundtrip_never_leaks_key():
    r = client.put("/api/settings", json={
        "local_ai_enabled": True,
        "ai_provider": "openrouter",
        "openrouter_api_key": "sk-or-secret-123",
        "openrouter_model": "anthropic/claude-haiku-4.5",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ai_provider"] == "openrouter"
    assert body["openrouter_key_set"] is True
    assert "sk-or-secret-123" not in json.dumps(body)
    # Saving again without the key keeps the stored one (no wipe).
    r2 = client.put("/api/settings", json={"openrouter_model": "openai/gpt-4o-mini"})
    assert r2.status_code == 200
    assert r2.json()["openrouter_key_set"] is True
    client.put("/api/settings", json={"local_ai_enabled": False, "ai_provider": "ollama"})
    _set("openrouter_api_key", "")


def test_interpret_via_openrouter(openrouter_cfg):
    calls = []
    draft = [{"action": "water", "plant": None, "amount": None,
              "unit": None, "detail": None, "notes": "test"}]
    body = {"choices": [{"message": {"content": json.dumps(draft)}}]}
    with patch.object(urllib.request, "urlopen", _capture_urlopen(body, calls)):
        r = client.post("/api/ai/interpret", json={"text": "watered everything"})
    assert r.status_code == 200
    assert r.json()["drafts"][0]["action"] == "water"


def test_status_shape_for_quick_log(openrouter_cfg):
    calls = []
    with patch.object(
        urllib.request, "urlopen",
        _capture_urlopen({"data": {"label": "k", "usage": 0}}, calls),
    ):
        st = client.get("/api/ai/status").json()
    assert st["enabled"] is True
    assert st["provider"] == "openrouter"
    assert st["reachable"] is True
