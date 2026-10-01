"""Tests for the v2.52.0 🎲 chaos garden pick — one random experimental plant
per year, never something the gardener has grown before.

Run:  cd ~/workspace/verdant && PYTHONPATH=. .venv/bin/python -m pytest tests/test_chaos_pick.py -q
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date as Date
from pathlib import Path

import pytest  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="chaos-pick-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402
from sqlmodel import select  # noqa: E402

from app import ai_tools as ai_tools_mod  # noqa: E402
from app import chaos as chaos_mod  # noqa: E402
from app.database import engine, get_session, init_db  # noqa: E402
from app.models import Harvest, Plant, SeedPacket, Setting, WishlistItem  # noqa: E402
from app.routers.chaos import router as chaos_router  # noqa: E402

assert get_session  # keep the conventional import used

init_db()

_test_app = FastAPI()
_test_app.include_router(chaos_router)
client = TestClient(_test_app)

YEAR = 2031  # fixed fake year — never collides with the real current year


@pytest.fixture
def session():
    with SQLSession(engine) as s:
        yield s


@pytest.fixture(autouse=True)
def _clean_chaos_state():
    yield
    with SQLSession(engine) as s:
        for row in s.exec(select(Setting)
                          .where(Setting.key.like("chaos_pick_%"))).all():
            s.delete(row)
        s.commit()


def _store(session, year, variety, rerolled=None):
    session.add(Setting(key=f"chaos_pick_{year}",
                        value=json.dumps({"variety": variety, "pitch": "p",
                                          "kind": "k", "picked_at": "2031-01-01",
                                          "accepted": False,
                                          "rerolled": rerolled or []})))
    session.commit()


###########################################################################
# Curated list
###########################################################################

def test_curated_list_size_and_shape():
    assert len(chaos_mod.CHAOS_VARIETIES) >= 28
    names = [e["name"] for e in chaos_mod.CHAOS_VARIETIES]
    assert len(names) == len(set(names)), "duplicate entries in the chaos list"
    for e in chaos_mod.CHAOS_VARIETIES:
        assert e["name"] and e["pitch"] and e["kind"] and e["match"], e


###########################################################################
# History exclusion
###########################################################################

def test_grown_variety_excluded(session):
    session.add(Plant(variety_name="Kohlrabi", species_type="Brassica",
                      status="Growing"))
    session.commit()
    try:
        names = [e["name"] for e in chaos_mod.eligible_varieties(session)]
        assert "Kohlrabi" not in names
    finally:
        for p in session.exec(select(Plant)
                              .where(Plant.variety_name == "Kohlrabi")).all():
            session.delete(p)
        session.commit()


def test_seed_stash_variety_excluded(session):
    session.add(SeedPacket(variety_name="Cucamelon", species_type="Cucumber"))
    session.commit()
    try:
        names = [e["name"] for e in chaos_mod.eligible_varieties(session)]
        assert "Cucamelon" not in names
    finally:
        for p in session.exec(select(SeedPacket)
                              .where(SeedPacket.variety_name == "Cucamelon")).all():
            session.delete(p)
        session.commit()


def test_harvest_log_variety_excluded(session):
    p = Plant(variety_name="Luffa Test Vine", species_type="Gourd",
              status="Growing")
    session.add(p)
    session.commit()
    session.refresh(p)
    session.add(Harvest(plant_id=p.id, date="2031-08-01", quantity=1))
    session.commit()
    try:
        names = [e["name"] for e in chaos_mod.eligible_varieties(session)]
        assert "Luffa" not in names  # "luffa test vine" matches the luffa entry
    finally:
        for h in session.exec(select(Harvest)
                              .where(Harvest.plant_id == p.id)).all():
            session.delete(h)
        session.delete(p)
        session.commit()


def test_prior_year_chaos_picks_excluded(session):
    _store(session, 2030, "Salsify")
    names = [e["name"] for e in chaos_mod.eligible_varieties(session)]
    assert "Salsify" not in names


def test_empty_history_all_eligible(session):
    names = [e["name"] for e in chaos_mod.eligible_varieties(session)]
    assert len(names) == len(chaos_mod.CHAOS_VARIETIES)


###########################################################################
# Pick stability + reroll behavior
###########################################################################

def test_pick_stable_within_year(session):
    first = chaos_mod.current_pick(session, YEAR)
    second = chaos_mod.current_pick(session, YEAR)
    assert first["variety"] == second["variety"]


def test_initial_draw_deterministic(session):
    a = chaos_mod.draw_initial(session, YEAR)["variety"]
    with SQLSession(engine) as s2:
        for row in s2.exec(select(Setting)
                           .where(Setting.key == f"chaos_pick_{YEAR}")).all():
            s2.delete(row)
        s2.commit()
    b = chaos_mod.draw_initial(session, YEAR)["variety"]
    assert a == b


def test_reroll_never_repeats_within_year(session):
    chaos_mod.current_pick(session, YEAR)
    seen = set()
    for _ in range(6):
        pick = chaos_mod.reroll(session, YEAR)
        assert pick["variety"] not in seen, f"{pick['variety']} repeated"
        seen.add(pick["variety"])
    stored = chaos_mod._read_raw(session, YEAR)
    assert len(stored["rerolled"]) == 6
    assert len(set(stored["rerolled"])) == 6


def test_preview_matches_reroll(session):
    chaos_mod.current_pick(session, YEAR)
    preview = chaos_mod.preview_reroll(session, YEAR)
    # Preview must not persist: stored pick unchanged.
    assert chaos_mod._read_raw(session, YEAR)["variety"] != preview["variety"]
    actual = chaos_mod.reroll(session, YEAR)
    assert actual["variety"] == preview["variety"]


def test_pinned_reroll_honored(session):
    chaos_mod.current_pick(session, YEAR)
    pick = chaos_mod.reroll(session, YEAR, pinned="Orach")
    assert pick["variety"] == "Orach"


def test_pinned_excluded_variety_falls_back(session):
    session.add(Plant(variety_name="Orach", species_type="Green",
                      status="Growing"))
    session.commit()
    try:
        chaos_mod.current_pick(session, YEAR)
        pick = chaos_mod.reroll(session, YEAR, pinned="Orach")
        assert pick["variety"] != "Orach"  # grown before → random fallback
    finally:
        for p in session.exec(select(Plant)
                              .where(Plant.variety_name == "Orach")).all():
            session.delete(p)
        session.commit()


###########################################################################
# Accept → order list
###########################################################################

def test_accept_marks_and_adds_to_order_list(session):
    pick = chaos_mod.current_pick(session, YEAR)
    variety = pick["variety"]
    out = chaos_mod.accept(session, YEAR)
    assert out["accepted"] is True
    items = [w for w in session.exec(select(WishlistItem)).all()
             if (w.variety_name or "").strip().lower() == variety.strip().lower()]
    assert len(items) == 1
    assert items[0].checked is True
    assert "chaos pick" in (items[0].notes or "").lower()
    # Double accept → no duplicate wishlist item.
    chaos_mod.accept(session, YEAR)
    items = [w for w in session.exec(select(WishlistItem)).all()
             if (w.variety_name or "").strip().lower() == variety.strip().lower()]
    assert len(items) == 1
    for w in items:
        session.delete(w)
    session.commit()


###########################################################################
# API
###########################################################################

def test_api_get_draws_and_returns_pick():
    r = client.get("/api/chaos-pick")
    assert r.status_code == 200
    body = r.json()
    assert body["variety"] and body["pitch"] and body["year"] == Date.today().year
    r2 = client.get("/api/chaos-pick")
    assert r2.json()["variety"] == body["variety"]  # stable once drawn


def test_api_reroll_changes_pick():
    first = client.get("/api/chaos-pick").json()["variety"]
    second = client.post("/api/chaos-pick/reroll").json()["variety"]
    assert second != first
    assert client.post("/api/chaos-pick/reroll").json()["rerolls"] >= 2


def test_api_accept():
    body = client.post("/api/chaos-pick/accept").json()
    assert body["accepted"] is True
    with SQLSession(engine) as s:
        items = [w for w in s.exec(select(WishlistItem)).all()
                 if (w.variety_name or "").strip().lower()
                 == body["variety"].strip().lower()]
        assert items and items[0].checked
        for w in items:
            s.delete(w)
        s.commit()


###########################################################################
# Chat tool
###########################################################################

def test_chat_tool_read_path(session):
    out = ai_tools_mod.execute_read(session, "chaos_pick", {})
    assert out["variety"]
    assert "chaos_pick" in ai_tools_mod.READ_TOOLS


def test_chat_tool_reroll_draft(session):
    d = ai_tools_mod.build_write_draft(session, "chaos_pick",
                                       {"action": "reroll"})
    assert d is not None
    assert d["action"] == "chaos_reroll"
    assert d["plant_name"] and d["notes"]
    # The pinned variety the draft shows is honored by the real reroll.
    out = chaos_mod.reroll(session, YEAR, pinned=d["plant_name"])
    assert out["variety"] == d["plant_name"]
