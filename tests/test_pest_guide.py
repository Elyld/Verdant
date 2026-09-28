"""Pest & disease guide endpoints (bundled database, no network).

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="pest-guide-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)

REQUIRED = ["slug", "name", "type", "hosts", "signs",
            "treatment_organic", "treatment_conventional", "prevention", "sources"]


def test_list_returns_all_entries():
    res = client.get("/api/pest-guide/")
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) == 40
    slugs = [e["slug"] for e in entries]
    assert len(set(slugs)) == len(slugs), "duplicate slugs"


def test_every_entry_has_full_fields():
    res = client.get("/api/pest-guide/aphids")
    assert res.status_code == 200
    entry = res.json()
    for field in REQUIRED:
        assert entry.get(field), f"aphids missing {field}"
    assert isinstance(entry["hosts"], list) and entry["hosts"]
    assert isinstance(entry["sources"], list) and entry["sources"]


def test_search_finds_by_name():
    res = client.get("/api/pest-guide/search", params={"q": "aphid"})
    assert res.status_code == 200
    names = [e["name"] for e in res.json()]
    assert names and names[0] == "Aphids"


def test_search_finds_by_host():
    res = client.get("/api/pest-guide/search", params={"q": "tomato"})
    assert res.status_code == 200
    slugs = [e["slug"] for e in res.json()]
    assert "tomato-hornworm" in slugs
    assert "early-blight" in slugs


def test_search_empty_query_returns_empty():
    res = client.get("/api/pest-guide/search", params={"q": ""})
    assert res.status_code == 200
    assert res.json() == []


def test_for_host_matches_singular_plural():
    singular = client.get("/api/pest-guide/for-host", params={"host": "tomato"}).json()
    plural = client.get("/api/pest-guide/for-host", params={"host": "tomatoes"}).json()
    assert singular and plural
    assert {e["slug"] for e in singular} == {e["slug"] for e in plural}


def test_for_host_squash():
    res = client.get("/api/pest-guide/for-host", params={"host": "squash"})
    assert res.status_code == 200
    slugs = [e["slug"] for e in res.json()]
    assert "squash-bugs" in slugs
    assert "squash-vine-borer" in slugs


def test_unknown_slug_404s():
    res = client.get("/api/pest-guide/not-a-real-pest")
    assert res.status_code == 404
