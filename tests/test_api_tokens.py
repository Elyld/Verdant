"""Scoped API tokens: creation, bearer auth, scope enforcement, revocation.

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="api-tokens-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession, select  # noqa: E402

from app import api_tokens as tokens_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiToken  # noqa: E402

init_db()
client = TestClient(app)


def _create(name="Hermes", scopes=("read", "invoices:write")):
    r = client.post("/api/api-tokens/", json={"name": name, "scopes": list(scopes)})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["token"], body["secret"]


def _auth(secret):
    return {"Authorization": f"Bearer {secret}"}


def _row(token_id):
    with SQLSession(engine) as s:
        return s.get(ApiToken, token_id)


# --- creation ----------------------------------------------------------------

def test_create_returns_plaintext_once_and_stores_only_hash():
    token, secret = _create(name="tok-once", scopes=["read"])
    assert secret.startswith("verdant_")
    assert len(secret) > len("verdant_") + 20  # 32 urlsafe bytes
    row = _row(token["id"])
    assert row is not None
    assert row.token_hash != secret  # plaintext never stored
    assert row.token_hash == hashlib.sha256(secret.encode()).hexdigest()
    assert len(row.token_hash) == 64


def test_create_rejects_unknown_scopes():
    r = client.post("/api/api-tokens/", json={"name": "bad", "scopes": ["nope:write"]})
    assert r.status_code == 422


def test_create_requires_name():
    r = client.post("/api/api-tokens/", json={"name": "   ", "scopes": []})
    assert r.status_code == 400


def test_list_leaks_no_secrets():
    token, secret = _create(name="tok-list", scopes=["read"])
    r = client.get("/api/api-tokens/")
    assert r.status_code == 200
    assert secret not in r.text
    assert "token_hash" not in r.text
    assert any(t["name"] == "tok-list" for t in r.json())


def test_scopes_endpoint_lists_vocabulary():
    r = client.get("/api/api-tokens/scopes")
    assert r.status_code == 200
    scopes = {s["scope"] for s in r.json()}
    assert {"*", "read", "invoices:write", "seed_packets:write"} <= scopes
    assert all(s.get("description") for s in r.json())


# --- bearer auth ---------------------------------------------------------------

def test_bearer_get_with_read_scope():
    _, secret = _create(name="tok-read", scopes=["read"])
    r = client.get("/api/invoices/", headers=_auth(secret))
    assert r.status_code == 200


def test_unknown_token_is_401():
    r = client.get("/api/invoices/", headers=_auth("verdant_doesnotexist"))
    assert r.status_code == 401


def test_revoked_token_is_401():
    token, secret = _create(name="tok-revoke", scopes=["read"])
    r = client.post(f"/api/api-tokens/{token['id']}/revoke")
    assert r.status_code == 200
    assert r.json()["token"]["revoked"] is True
    r = client.get("/api/invoices/", headers=_auth(secret))
    assert r.status_code == 401


def test_valid_token_missing_scope_is_403():
    _, secret = _create(name="tok-narrow", scopes=["read"])
    # read scope: GET fine…
    r = client.get("/api/plants/", headers=_auth(secret))
    assert r.status_code == 200
    # …but POST needs plants:write
    r = client.post("/api/plants/", json={"variety_name": "x"}, headers=_auth(secret))
    assert r.status_code == 403


def test_star_scope_passes_everything():
    _, secret = _create(name="tok-star", scopes=["*"])
    assert client.get("/api/invoices/", headers=_auth(secret)).status_code == 200
    r = client.post("/api/plants/", json={"variety_name": "Star Test", "species_type": "Tomato"},
                    headers=_auth(secret))
    # 201 created or 422 validation — either way, auth passed (not 401/403)
    assert r.status_code in (201, 422), r.text


def test_write_scope_allows_writes_in_its_domain():
    _, secret = _create(name="tok-pw", scopes=["plants:write"])
    r = client.post("/api/plants/", json={"variety_name": "Token Grown", "species_type": "Tomato"},
                    headers=_auth(secret))
    assert r.status_code in (201, 422), r.text


# --- local-trust passthrough -----------------------------------------------------

def test_no_header_requests_still_work():
    # The web UI sends no credentials; scoped endpoints must behave as before.
    r = client.get("/api/invoices/")
    assert r.status_code == 200
    r = client.get("/api/seed-packets/")
    assert r.status_code == 200
    # POST without a header reaches endpoint validation, not an auth wall.
    r = client.post("/api/invoices/", json={"vendor": "x"})
    assert r.status_code in (201, 422), r.text


def test_non_bearer_scheme_passes_through():
    r = client.get("/api/invoices/", headers={"Authorization": "Basic abc123"})
    assert r.status_code == 200


# --- last_used_at ------------------------------------------------------------------

def test_last_used_at_updates_on_authed_request():
    token, secret = _create(name="tok-used", scopes=["read"])
    assert _row(token["id"]).last_used_at is None
    client.get("/api/invoices/", headers=_auth(secret))
    assert _row(token["id"]).last_used_at is not None


def test_last_used_at_untouched_by_anonymous_requests():
    token, _ = _create(name="tok-unused", scopes=["read"])
    client.get("/api/invoices/")
    assert _row(token["id"]).last_used_at is None
