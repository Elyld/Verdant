"""New chat tools for v2.48.0 (ai-powerhouse): season_advice, save_memory_note,
recall_notes, variety_performance.

Run with:  pytest -q
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="ai-powerhouse-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from sqlmodel import Session as SQLSession  # noqa: E402
from sqlmodel import select as _select  # noqa: E402

from app import ai_tools as ai_tools_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.models import Harvest, ObservationLog, Plant  # noqa: E402

init_db()


@pytest.fixture
def garden():
    created = {"plants": [], "harvests": [], "observations": []}
    with SQLSession(engine) as s:
        tomato = Plant(variety_name="Cherokee Purple", species_type="Tomato",
                       status="Growing")
        pepper = Plant(variety_name="Bell Pepper", species_type="Pepper",
                       status="Growing")
        s.add(tomato)
        s.add(pepper)
        s.commit()
        s.refresh(tomato)
        s.refresh(pepper)
        created["plants"] = [tomato.id, pepper.id]

        for pid, d, qty, wt, wunit in (
            (tomato.id, "2025-08-01", 6, 24.0, "oz"),
            (tomato.id, "2025-08-15", 4, 0.5, "lb"),
            (tomato.id, "2026-08-01", 10, 1.5, "lb"),
            (tomato.id, "2026-08-20", 7, 12.0, "oz"),
            (pepper.id, "2025-09-01", 3, 8.0, "oz"),
            (pepper.id, "2026-09-05", 5, 12.0, "oz"),
        ):
            h = Harvest(plant_id=pid, date=d, quantity=qty,
                        weight=wt, weight_unit=wunit)
            s.add(h)
            s.commit()
            s.refresh(h)
            created["harvests"].append(h.id)

        mem = ObservationLog(date="2026-09-20", plant_name="Notebook",
                             notes="loves Cherokee Purple tomatoes — best slicer ever")
        reg = ObservationLog(date="2026-09-15", plant_name="Cherokee Purple",
                             plant_id=tomato.id,
                             notes="Cherokee Purple fruit starting to blush")
        s.add(mem)
        s.add(reg)
        s.commit()
        s.refresh(mem)
        s.refresh(reg)
        created["observations"] = [mem.id, reg.id]
    yield created
    with SQLSession(engine) as s:
        for hid in created["harvests"]:
            row = s.get(Harvest, hid)
            if row:
                s.delete(row)
        for oid in created["observations"]:
            row = s.get(ObservationLog, oid)
            if row:
                s.delete(row)
        for pid in created["plants"]:
            row = s.get(Plant, pid)
            if row:
                s.delete(row)
        s.commit()


def test_season_advice(garden):
    with SQLSession(engine) as s:
        result = ai_tools_mod.execute_read(s, "season_advice", {})
    assert "days_to_frost" in result
    assert "first_frost" in result
    assert "garlic" in " ".join(result["advice"]).lower()
    assert all(len(a) <= 140 for a in result["advice"])
    assert all(isinstance(a, str) for a in result["advice"])


def test_save_memory_note_draft(garden):
    with SQLSession(engine) as s:
        d = ai_tools_mod.build_write_draft(
            s, "save_memory_note", {"note": "prefers morning watering"})
    assert d is not None
    assert d["action"] == "note"
    assert d["plant_name"] == "Notebook"
    assert "morning watering" in d["notes"]

    with SQLSession(engine) as s:
        d2 = ai_tools_mod.build_write_draft(
            s, "save_memory_note",
            {"note": "mulch heavily", "plant": "Cherokee Purple"})
    assert d2 is not None
    assert d2["action"] == "note"
    assert d2["plant_name"] == "Cherokee Purple"


def test_save_memory_note_empty(garden):
    with SQLSession(engine) as s:
        assert ai_tools_mod.build_write_draft(
            s, "save_memory_note", {"note": "  "}) is None
        assert ai_tools_mod.build_write_draft(
            s, "save_memory_note", {}) is None


def test_recall_notes(garden):
    with SQLSession(engine) as s:
        result = ai_tools_mod.execute_read(s, "recall_notes", {"query": "cherokee"})
    assert result["matches"], result
    first = result["matches"][0]
    assert first["memory"] is True
    assert "loves" in first["notes"]
    # Memory notes come first, regular notes after.
    memories = [m for m in result["matches"] if m["memory"]]
    regulars = [m for m in result["matches"] if not m["memory"]]
    assert result["matches"][: len(memories)] == memories
    assert regulars, "expected the regular observation note too"


def test_recall_notes_blank(garden):
    with SQLSession(engine) as s:
        result = ai_tools_mod.execute_read(s, "recall_notes", {"query": ""})
    assert "error" in result


def test_variety_performance(garden):
    with SQLSession(engine) as s:
        result = ai_tools_mod.execute_read(s, "variety_performance", {})
    by_name = {v["variety"]: v for v in result["varieties"]}
    assert "Cherokee Purple" in by_name
    cp = by_name["Cherokee Purple"]
    assert cp["years"]["2026"] == {"harvests": 2, "quantity": 17, "weight_oz": 36.0}
    assert cp["years"]["2025"] == {"harvests": 2, "quantity": 10, "weight_oz": 32.0}
    assert cp["total_harvests"] == 4
    assert cp["total_quantity"] == 27
    # Sorted by total_quantity desc.
    totals = [v["total_quantity"] for v in result["varieties"]]
    assert totals == sorted(totals, reverse=True)


def test_variety_performance_filtered(garden):
    with SQLSession(engine) as s:
        result = ai_tools_mod.execute_read(s, "variety_performance",
                                           {"variety": "bell"})
    assert [v["variety"] for v in result["varieties"]] == ["Bell Pepper"]
    bp = result["varieties"][0]
    assert bp["years"]["2026"] == {"harvests": 1, "quantity": 5, "weight_oz": 12.0}


def test_tools_catalogue_lists_new_tools():
    names = {t["name"] for t in ai_tools_mod.TOOLS}
    new = {"season_advice", "save_memory_note", "recall_notes",
           "variety_performance"}
    assert new <= names
    assert {"season_advice", "recall_notes",
            "variety_performance"} <= ai_tools_mod.READ_TOOLS
    assert ai_tools_mod.WRITE_TOOL_ACTIONS["save_memory_note"] == "note"
    for tool_name in ("season_advice", "recall_notes", "variety_performance"):
        assert tool_name in ai_tools_mod._READ_EXEC
