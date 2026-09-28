"""Crop lookup endpoints (bundled database, no network).

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="crops-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import crops as crops_mod  # noqa: E402

init_db()
client = TestClient(app)


def test_search_matches_name():
    r = client.get("/api/crops", params={"q": "tomato"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    names = [c["name"] for c in body["crops"]]
    assert "Tomato" in names
    # summary shape — no description dump in list results
    first = body["crops"][0]
    assert set(first) == {"key", "name", "family", "sun", "days_to_maturity"}


def test_search_matches_alias():
    r = client.get("/api/crops", params={"q": "habanero"})
    names = [c["name"] for c in r.json()["crops"]]
    assert "Pepper (Hot)" in names


def test_search_is_case_insensitive():
    r = client.get("/api/crops", params={"q": "BASIL"})
    assert any(c["key"] == "basil" for c in r.json()["crops"])


def test_search_empty_query_returns_empty():
    assert client.get("/api/crops", params={"q": ""}).json()["crops"] == []
    assert client.get("/api/crops").json()["crops"] == []


def test_search_no_match():
    r = client.get("/api/crops", params={"q": "moon cactus"})
    assert r.json() == {"ok": True, "crops": []}


def test_search_caps_results():
    r = client.get("/api/crops", params={"q": "a"})  # matches almost everything
    assert len(r.json()["crops"]) <= 20


def test_detail_full_shape():
    r = client.get("/api/crops/tomato")
    assert r.status_code == 200
    crop = r.json()["crop"]
    assert crop["name"] == "Tomato"
    assert crop["sun"] == "Full Sun"
    assert crop["spacing_in"] == "24–36"
    assert crop["sowing_depth_in"] == "¼"
    assert crop["days_to_germination"] == "5–10"
    assert isinstance(crop["days_to_maturity"], int)
    assert len(crop["description"]) > 20


def test_detail_unknown_is_404():
    r = client.get("/api/crops/moon-cactus")
    assert r.status_code == 404


def test_every_crop_has_plantable_fields():
    """The database must carry the fields the form auto-fills."""
    for crop in crops_mod._crops():
        assert crop["sun"], crop["key"]
        assert crop["spacing_in"], crop["key"]
        assert crop["sowing_depth_in"], crop["key"]
        assert crop["days_to_maturity"], crop["key"]
