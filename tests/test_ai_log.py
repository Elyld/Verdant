"""Local-AI "tell it what you did" (Ollama stubbed).

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from urllib.error import URLError

import pytest

TMP = Path(tempfile.mkdtemp(prefix="ai-log-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402

from app import frost as frost_mod  # noqa: E402
from app import llm as llm_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Harvest, ObservationLog, Plant, WateringLog  # noqa: E402
from app.routers import ai_log  # noqa: E402

init_db()
client = TestClient(app)


def _set_ai(enabled: bool) -> None:
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "local_ai_enabled", "true" if enabled else "false")
        frost_mod.set_setting(s, "local_ai_base_url", "http://localhost:11434")
        frost_mod.set_setting(s, "local_ai_model", "qwen3:4b")
        s.commit()


@pytest.fixture
def ai_on():
    _set_ai(True)
    created = []
    with SQLSession(engine) as s:
        for name, species in (("Cherokee Purple", "Tomato"), ("Genovese Basil", "Basil")):
            p = Plant(variety_name=name, species_type=species, status="Growing")
            s.add(p)
            s.commit()
            s.refresh(p)
            created.append(p.id)
        s.commit()
    yield
    _set_ai(False)
    with SQLSession(engine) as s:
        for pid in created:
            p = s.get(Plant, pid)
            if p:
                s.delete(p)
        # interpret never writes, but be thorough: remove anything this module made
        for log in s.query(WateringLog).all():
            s.delete(log)
        for h in s.query(Harvest).all():
            if h.plant_id in created:
                s.delete(h)
        for o in s.query(ObservationLog).all():
            if (o.notes or "") == "ai-log-test":
                s.delete(o)
        s.commit()


@pytest.fixture(autouse=True)
def _ai_off():
    _set_ai(False)
    yield
    _set_ai(False)


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub_ollama(monkeypatch, chat_content=None, tags_ok=True, error=None, tags_models=None):
    """Stub urllib.request.urlopen for the Ollama endpoints."""
    calls = []

    def fake(request, timeout=None):
        calls.append(request.full_url)
        if error is not None:
            raise error
        method = request.get_method()
        if request.full_url.endswith("/api/tags"):
            # Ollama's /api/tags is GET-only (POST → 405) — pin the method.
            assert method == "GET", f"/api/tags must be GET, got {method}"
            models = tags_models if tags_models is not None else ([{"name": "qwen3:4b"}] if tags_ok else [])
            body = {"models": models} if tags_ok or tags_models is not None else {}
        elif request.full_url.endswith("/api/chat"):
            assert method == "POST", f"/api/chat must be POST, got {method}"
            body = {"message": {"content": chat_content or ""}, "done": True}
        else:
            raise AssertionError(f"unexpected URL {request.full_url}")
        return _FakeResponse(json.dumps(body).encode("utf-8"))

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls


CHAT_MULTI = json.dumps([
    {"action": "water", "plant": "Cherokee Purple", "amount": None, "unit": None,
     "detail": None, "notes": "morning watering"},
    {"action": "harvest", "plant": "Genovese Basil", "amount": 3, "unit": None,
     "detail": None, "notes": "for pesto"},
    {"action": "fertilize", "plant": "Cherokee Purple", "amount": 2, "unit": "tbsp",
     "detail": "fish emulsion", "notes": ""},
])


# --------------------------------------------------------------------------- #
# /api/ai/status
# --------------------------------------------------------------------------- #
def test_status_disabled(ai_on, monkeypatch):
    _set_ai(False)
    r = client.get("/api/ai/status")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_status_reachable(ai_on, monkeypatch):
    _stub_ollama(monkeypatch)
    r = client.get("/api/ai/status")
    body = r.json()
    assert body["enabled"] is True and body["reachable"] is True
    assert body["model"] == "qwen3:4b"
    assert body["model_present"] is True


def test_status_model_missing(ai_on, monkeypatch):
    _stub_ollama(monkeypatch, tags_models=[{"name": "llama3:8b"}])
    body = client.get("/api/ai/status").json()
    assert body["reachable"] is True
    assert body["model_present"] is False


def test_status_strips_v1_from_base_url(ai_on, monkeypatch):
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "local_ai_base_url", "http://localhost:11434/v1")
        s.commit()
    calls = _stub_ollama(monkeypatch)
    body = client.get("/api/ai/status").json()
    assert body["reachable"] is True
    assert calls and all("/v1" not in u for u in calls), calls


def test_normalize_base_url():
    assert llm_mod._normalize_base_url("http://x:11434/v1") == "http://x:11434"
    assert llm_mod._normalize_base_url("http://x:11434/v1/") == "http://x:11434"
    assert llm_mod._normalize_base_url("http://x:11434/") == "http://x:11434"
    assert llm_mod._normalize_base_url("http://x:11434") == "http://x:11434"
    assert llm_mod._normalize_base_url("") == llm_mod.DEFAULT_OLLAMA_BASE


def test_status_unreachable_localhost_hint(ai_on, monkeypatch):
    _stub_ollama(monkeypatch, error=URLError("no server"))
    body = client.get("/api/ai/status").json()
    assert body["reachable"] is False
    assert "host.docker.internal" in body["hint"]


def test_status_unreachable_friendly(ai_on, monkeypatch):
    _stub_ollama(monkeypatch, error=URLError("no server"))
    r = client.get("/api/ai/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True and body["reachable"] is False
    assert "http://localhost:11434" in body["hint"]


def test_status_unreachable_includes_error_detail(ai_on, monkeypatch):
    _stub_ollama(monkeypatch, error=URLError("[Errno 111] Connection refused"))
    body = client.get("/api/ai/status").json()
    assert body["reachable"] is False
    assert "URLError" in body["error"]
    assert "Connection refused" in body["error"]


def test_interpret_surfaces_server_error(ai_on, monkeypatch):
    import io
    from urllib.error import HTTPError
    said = json.dumps({"error": 'model "qwen3:4b" not found'}).encode("utf-8")
    err = HTTPError("http://x/api/chat", 404, "Not Found", {}, io.BytesIO(said))
    _stub_ollama(monkeypatch, error=err)
    r = client.post("/api/ai/interpret", json={"text": "watered the tomatoes"})
    assert r.status_code == 502
    assert "not found" in r.json()["detail"]


def test_interpret_timeout_hint(ai_on, monkeypatch):
    import socket
    _stub_ollama(monkeypatch, error=socket.timeout("timed out"))
    r = client.post("/api/ai/interpret", json={"text": "watered the tomatoes"})
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "timed out" in detail.lower()
    assert "still be loading" in detail


# --------------------------------------------------------------------------- #
# /api/ai/interpret
# --------------------------------------------------------------------------- #
def test_interpret_multi_action(ai_on, monkeypatch):
    calls = _stub_ollama(monkeypatch, chat_content=CHAT_MULTI)
    r = client.post("/api/ai/interpret", json={"text": "watered the tomatoes and harvested basil"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    drafts = body["drafts"]
    assert len(drafts) == 3
    assert drafts[0]["action"] == "water" and drafts[0]["plant_name"] == "Cherokee Purple"
    assert drafts[0]["plant_id"] is not None
    assert drafts[1]["action"] == "harvest" and drafts[1]["amount"] == 3
    assert drafts[2]["action"] == "fertilize" and drafts[2]["detail"] == "fish emulsion"
    assert any("api/chat" in c for c in calls)
    # interpret must never write
    with SQLSession(engine) as s:
        assert s.query(WateringLog).count() == 0


def test_interpret_garbage_returns_empty_with_message(ai_on, monkeypatch):
    _stub_ollama(monkeypatch, chat_content="I am a teapot, hear me roar")
    r = client.post("/api/ai/interpret", json={"text": "blarg"})
    assert r.status_code == 200
    body = r.json()
    assert body["drafts"] == []
    assert body["message"]


def test_interpret_fenced_json(ai_on, monkeypatch):
    fenced = "```json\n" + CHAT_MULTI + "\n```"
    _stub_ollama(monkeypatch, chat_content=fenced)
    r = client.post("/api/ai/interpret", json={"text": "did stuff"})
    assert r.json()["drafts"] != []


def test_interpret_unreachable_is_502(ai_on, monkeypatch):
    _stub_ollama(monkeypatch, error=URLError("no server"))
    r = client.post("/api/ai/interpret", json={"text": "watered the tomatoes"})
    assert r.status_code == 502
    assert "localhost:11434" in r.json()["detail"]
    assert "Traceback" not in r.json()["detail"]


def test_interpret_disabled_is_400(monkeypatch):
    _set_ai(False)
    r = client.post("/api/ai/interpret", json={"text": "watered the tomatoes"})
    assert r.status_code == 400


def test_interpret_empty_is_400(ai_on):
    r = client.post("/api/ai/interpret", json={"text": "   "})
    assert r.status_code == 400


def test_interpret_unknown_plant_kept_as_note(ai_on, monkeypatch):
    chat = json.dumps([{"action": "water", "plant": "Moon Cactus", "amount": None,
                        "unit": None, "detail": None, "notes": "the moon cactus"}])
    _stub_ollama(monkeypatch, chat_content=chat)
    r = client.post("/api/ai/interpret", json={"text": "watered the moon cactus"})
    drafts = r.json()["drafts"]
    assert len(drafts) == 1
    assert drafts[0]["plant_name"] is None  # user picks it in the UI
    assert drafts[0]["plant_id"] is None


# --------------------------------------------------------------------------- #
# unit-level: extraction + cleaning
# --------------------------------------------------------------------------- #
def test_extract_json_array_variants():
    assert ai_log._extract_json_array('[{"a": 1}]') == [{"a": 1}]
    assert ai_log._extract_json_array('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert ai_log._extract_json_array('Some prose [{"a": 1}] trailing') == [{"a": 1}]
    assert ai_log._extract_json_array('no json here') is None
    assert ai_log._extract_json_array('{"not": "an array"}') is None


def test_clean_draft_rejects_junk():
    plants = ["Cherokee Purple"]
    assert ai_log._clean_draft({"action": "teleport", "plant": "Cherokee Purple"}, plants) is None
    assert ai_log._clean_draft("nope", plants) is None
    d = ai_log._clean_draft({"action": "water", "plant": "cherokee purple", "notes": "x"}, plants)
    assert d["plant_name"] == "Cherokee Purple"  # case-insensitive match
    d2 = ai_log._clean_draft({"action": "harvest", "plant": None, "amount": "abc"}, plants)
    assert d2["amount"] is None
