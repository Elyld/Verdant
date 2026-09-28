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
    names = [c["name"] for c in body["guide"]]
    assert "Tomato" in names
    # summary shape — no description dump in list results
    first = body["guide"][0]
    assert set(first) == {"kind", "key", "name", "crop_name", "family", "sun",
                          "days_to_maturity", "maturity_source", "community", "note"}
    assert first["kind"] == "crop"


def test_search_matches_alias():
    r = client.get("/api/crops", params={"q": "habanero"})
    guide = r.json()["guide"]
    assert any(c["kind"] == "variety" and c["name"] == "Habanero" for c in guide)


def test_search_matches_variety():
    r = client.get("/api/crops", params={"q": "cherokee"})
    guide = r.json()["guide"]
    match = next(c for c in guide if c["name"] == "Cherokee Purple")
    assert match["kind"] == "variety"
    assert match["key"] == "tomato"
    assert match["crop_name"] == "Tomato"
    assert match["days_to_maturity"] == 80  # variety override, not the crop default


def test_search_is_case_insensitive():
    r = client.get("/api/crops", params={"q": "BASIL"})
    assert any(c["key"] == "basil" for c in r.json()["guide"])


def test_search_empty_query_returns_empty():
    assert client.get("/api/crops", params={"q": ""}).json() == {"ok": True, "guide": [], "stash": []}
    assert client.get("/api/crops").json() == {"ok": True, "guide": [], "stash": []}


def test_search_no_match():
    r = client.get("/api/crops", params={"q": "moon cactus"})
    assert r.json() == {"ok": True, "guide": [], "stash": []}


def test_search_caps_results():
    r = client.get("/api/crops", params={"q": "a"})  # matches almost everything
    assert len(r.json()["guide"]) <= 20


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
    assert crop["source"] == "Built-in crop guide"
    assert any(v["name"] == "Cherokee Purple" for v in crop["varieties"])


def test_detail_unknown_is_404():
    r = client.get("/api/crops/moon-cactus")
    assert r.status_code == 404


def test_search_finds_seed_stash():
    """A packet in the stash matches by variety name."""
    from sqlmodel import Session as SQLSession
    from app.database import engine
    from app.models import SeedPacket
    with SQLSession(engine) as s:
        p = SeedPacket(variety_name="Cherokee Purple Test", species_type="Tomato",
                       vendor_name="Test Vendor", year_acquired=2025)
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
    try:
        body = client.get("/api/crops", params={"q": "cherokee purple test"}).json()
        assert any(e["kind"] == "packet" and e["packet_id"] == pid
                   for e in body["stash"])
        entry = next(e for e in body["stash"] if e["packet_id"] == pid)
        assert entry["vendor_name"] == "Test Vendor"
    finally:
        with SQLSession(engine) as s:
            p = s.get(SeedPacket, pid)
            if p:
                s.delete(p)
                s.commit()


def test_every_crop_has_plantable_fields():
    """The database must carry the fields the form auto-fills."""
    for crop in crops_mod._crops():
        assert crop["sun"], crop["key"]
        assert crop["spacing_in"], crop["key"]
        assert crop["sowing_depth_in"], crop["key"]
        assert crop["days_to_maturity"], crop["key"]
