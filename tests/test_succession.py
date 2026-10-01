"""Succession suggestion tests: free-container detection, frost math, rotation filter.

Run with:  pytest -q      (shares the same temp DB as test_api.py)
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="succession-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from app import succession as succession_mod  # noqa: E402
from app.database import get_session, init_db  # noqa: E402
from app.models import Container, Plant, Planting  # noqa: E402

YEAR = 2031
TODAY = date(YEAR, 7, 15)
FROST = date(YEAR, 10, 20)  # 97 days out


@pytest.fixture(scope="module")
def session():
    init_db()
    s = next(get_session())
    # Container A: completely empty -> free
    # Container B: growing plant -> occupied
    # Container C: finished tomato -> free, nightshade family excluded
    a = Container(name="Bag A", kind="grow bag", season_year=YEAR)
    b = Container(name="Bag B", kind="grow bag", season_year=YEAR)
    c = Container(name="Bag C", kind="grow bag", season_year=YEAR)
    s.add_all([a, b, c])
    s.commit()
    for cont in (a, b, c):
        s.refresh(cont)
    growing = Plant(variety_name="Basil Test", species_type="Basil", status="Growing")
    finished = Plant(variety_name="Cherokee Purple", species_type="Tomato", status="Finished")
    s.add_all([growing, finished])
    s.commit()
    s.refresh(growing)
    s.refresh(finished)
    s.add(Planting(container_id=b.id, plant_id=growing.id, season_year=YEAR))
    s.add(Planting(container_id=c.id, plant_id=finished.id, season_year=YEAR))
    s.commit()
    mine = {
        Planting: [p.id for p in s.query(Planting).filter(
            Planting.container_id.in_([a.id, b.id, c.id])).all()],
        Plant: [growing.id, finished.id],
        Container: [a.id, b.id, c.id],
    }
    yield s
    # Delete only our own rows: other modules share this DB, and nulling
    # their harvests' plant_id violates the NOT NULL constraint.
    for m in (Planting, Plant, Container):
        for row_id in mine[m]:
            row = s.get(m, row_id)
            if row is not None:
                s.delete(row)
    s.commit()
    s.close()


def test_free_containers_detected(session):
    out = succession_mod.suggestions(session, year=YEAR, today=TODAY, first_frost=FROST)
    assert out["ok"] is True
    assert out["first_frost"] == FROST.isoformat()
    assert out["days_left"] == 97
    names = [c["container_name"] for c in out["containers"]]
    assert "Bag A" in names
    assert "Bag C" in names
    assert "Bag B" not in names  # still growing


def test_suggestions_fit_before_frost(session):
    out = succession_mod.suggestions(session, year=YEAR, today=TODAY, first_frost=FROST)
    for c in out["containers"]:
        for s in c["suggestions"]:
            sow_by = date.fromisoformat(s["sow_by"])
            assert sow_by >= TODAY
            assert s["days_to_maturity"] + succession_mod.BUFFER_DAYS <= 97
    # most urgent (earliest sow_by) first
    for c in out["containers"]:
        sow_bys = [s["sow_by"] for s in c["suggestions"]]
        assert sow_bys == sorted(sow_bys)
        assert len(sow_bys) <= succession_mod.MAX_SUGGESTIONS


def test_rotation_filter_excludes_last_family(session):
    out = succession_mod.suggestions(session, year=YEAR, today=TODAY, first_frost=FROST)
    bag_c = next(c for c in out["containers"] if c["container_name"] == "Bag C")
    assert "Nightshade (Solanaceae)" in bag_c["last_families"]
    for s in bag_c["suggestions"]:
        assert s["family"] != "Nightshade (Solanaceae)"


def test_no_frost_note_without_location(session):
    out = succession_mod.suggestions(session, year=YEAR, today=TODAY, first_frost=None)
    # resolve_frost with no settings configured -> None in this temp DB
    if out["first_frost"] is None:
        for c in out["containers"]:
            assert "Settings" in c["note"]


def test_match_crop():
    assert succession_mod.match_crop("Cherokee Purple")["key"] == "tomato"
    assert succession_mod.match_crop("basil")["key"] == "basil"
    assert succession_mod.match_crop("") is None
    assert succession_mod.match_crop("something made up xyz") is None


def test_october_fallback_note(session):
    oct_today = date(YEAR, 10, 5)
    out = succession_mod.suggestions(session, year=YEAR, today=oct_today, first_frost=FROST)
    for c in out["containers"]:
        if not c["suggestions"]:
            assert "garlic" in c["note"].lower() or "cover crop" in c["note"].lower()


def test_microgreens_never_suggested(session):
    # Even with a whole year to play with, tray crops don't belong in a bag.
    out = succession_mod.suggestions(
        session, year=YEAR, today=date(YEAR, 1, 2), first_frost=date(YEAR, 12, 1)
    )
    for c in out["containers"]:
        for s in c["suggestions"]:
            name = s["name"].lower()
            assert "microgreen" not in name and "sprout" not in name
