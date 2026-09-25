"""Seed Sources tab tests: page renders, nav links present, CRUD works.

Run with:  pytest -q      (shares the same temp DB as test_api.py)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="seeds-test-"))
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


PAGES = ["/", "/observations", "/calendar", "/photos", "/plants", "/seeds", "/review"]


def test_seeds_page_renders(client):
    res = client.get("/seeds")
    assert res.status_code == 200
    assert "Seed Sources" in res.text
    assert 'id="seed-form"' in res.text


def test_nav_link_on_every_page(client):
    for page in PAGES:
        res = client.get(page)
        assert res.status_code == 200, page
        assert 'href="/seeds"' in res.text, f"missing Seeds nav on {page}"


def test_seed_source_crud(client):
    created = client.post("/api/seed-sources/", json={
        "source_id": "SRC-test-1",
        "source": "Territorial Seed",
        "variety": "Cherokee Purple",
        "type": "Vendor Purchase",
        "acquired_date": "2026-02-01",
        "notes": "test packet",
    })
    assert created.status_code == 201, created.text
    src_id = created.json()["id"]

    listed = client.get("/api/seed-sources/")
    assert any(s["variety"] == "Cherokee Purple" for s in listed.json())

    patched = client.patch(f"/api/seed-sources/{src_id}", json={"notes": "updated"})
    assert patched.status_code == 200
    assert patched.json()["notes"] == "updated"

    deleted = client.delete(f"/api/seed-sources/{src_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/seed-sources/{src_id}").status_code == 404
