"""Tunnel-ready security tests: headers, docs toggle, rate limiting.

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="security-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in r.headers["Permissions-Policy"]


def test_no_hsts_by_default(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_in_tunnel_mode(client, monkeypatch):
    monkeypatch.setenv("TUNNEL_MODE", "true")
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["Strict-Transport-Security"] == "max-age=31536000"


def test_docs_enabled_by_default(client, monkeypatch):
    monkeypatch.delenv("TUNNEL_MODE", raising=False)
    monkeypatch.delenv("DOCS_ENABLED", raising=False)
    r = client.get("/docs")
    assert r.status_code == 200


def test_docs_disabled_in_tunnel_mode(client, monkeypatch):
    monkeypatch.setenv("TUNNEL_MODE", "true")
    monkeypatch.delenv("DOCS_ENABLED", raising=False)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    # ...but the app itself still works
    assert client.get("/api/health").status_code == 200


def test_docs_explicit_override_wins(client, monkeypatch):
    monkeypatch.setenv("TUNNEL_MODE", "true")
    monkeypatch.setenv("DOCS_ENABLED", "true")
    assert client.get("/docs").status_code == 200


def test_footer_docs_link_by_default(client, monkeypatch):
    monkeypatch.delenv("TUNNEL_MODE", raising=False)
    monkeypatch.delenv("DOCS_ENABLED", raising=False)
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/docs"' in r.text


def test_rate_limit_kicks_in(monkeypatch):
    # Isolated app: the shared test client's limiter bucket already holds
    # requests from other test modules, so exercise a fresh instance.
    from fastapi import FastAPI

    from app.security import RateLimitMiddleware

    inner = FastAPI()

    @inner.get("/api/things")
    def things():
        return {"ok": True}

    @inner.get("/api/health")
    def health():
        return {"ok": True}

    inner.add_middleware(RateLimitMiddleware)
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    with TestClient(inner) as c:
        for _ in range(3):
            assert c.get("/api/things").status_code == 200
        r = c.get("/api/things")
        assert r.status_code == 429
        assert r.headers["Retry-After"] == "60"
        # health stays reachable even when limited
        assert c.get("/api/health").status_code == 200


def test_rate_limit_disabled_at_zero(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    for _ in range(10):
        assert client.get("/api/plants").status_code == 200
