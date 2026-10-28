"""Yearbook grounding: the season story and numbers table must not invent
facts or render missing weights as zero (Hermes defect report, 2026-10-28).

A 2041 season: one unweighed variety, one weighed variety, a dead plant
with a recorded cause, a dead plant with empty notes, one pest-log entry,
and an observation — so the prompt and the table both have real records
to stay faithful to. Variety names and the year are unique to this file
so a full-suite run sharing one temp DB can't collide with other modules.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="yearbook-grounding-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from sqlmodel import Session  # noqa: E402

from app import yearbook as yearbook_mod  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.models import Expense, Harvest, ObservationLog, PestLog, Plant  # noqa: E402

YEAR = 2041


@pytest.fixture(scope="module")
def seeded():
    init_db()
    with Session(engine) as s:
        pepper = Plant(variety_name="Grounding Pepper", species_type="Pepper",
                       category="Annual")
        tomato = Plant(variety_name="Grounding Tomato", species_type="Tomato",
                       category="Annual")
        raspberry = Plant(variety_name="Grounding Raspberry", species_type="Berry",
                          category="Perennial", status="Dead",
                          notes="Died 2041 - under-watered through the season.")
        mystery = Plant(variety_name="Grounding Mystery", species_type="Berry",
                        category="Perennial", status="Dead")
        s.add(pepper)
        s.add(tomato)
        s.add(raspberry)
        s.add(mystery)
        s.commit()
        for p in (pepper, tomato, raspberry, mystery):
            s.refresh(p)
        # Unweighed: 5 + 3 fruit, weight null — the "0.0 oz" trap.
        s.add(Harvest(plant_id=pepper.id, date=f"{YEAR}-08-19", quantity=5,
                      unit="fruit", weight=None, weight_unit="oz"))
        s.add(Harvest(plant_id=pepper.id, date=f"{YEAR}-08-20", quantity=3,
                      unit="fruit", weight=None, weight_unit="oz"))
        s.add(Harvest(plant_id=tomato.id, date=f"{YEAR}-08-19", quantity=2,
                      unit="fruit", weight=16.0, weight_unit="oz"))
        s.add(PestLog(date=f"{YEAR}-10-26",
                      pest_name="White grubs (scarab beetle larvae)",
                      plant_id=pepper.id))
        s.add(ObservationLog(date=f"{YEAR}-07-14", plant_name="Grounding Pepper",
                             plant_id=pepper.id,
                             notes="Mite stippling (unconfirmed)"))
        s.add(Expense(date=f"{YEAR}-04-01", category="Seeds",
                      description="pepper seeds", amount=10.0, plant_id=pepper.id))
        s.commit()
        yield


def test_unweighed_variety_flagged(seeded):
    with Session(engine) as s:
        stats = yearbook_mod.build_yearbook_stats(s, YEAR)
    by_variety = {v["variety"]: v for v in stats["varieties"]}
    assert by_variety["Grounding Pepper"]["has_weight"] is False
    assert by_variety["Grounding Tomato"]["has_weight"] is True
    assert stats["has_weight_any"] is True
    assert stats["total_qty"] == 10


def test_weight_cell_never_zero_for_missing():
    assert yearbook_mod._weight_cell(
        {"harvest_events": 0, "total_oz": 0.0}) == "—"
    assert yearbook_mod._weight_cell(
        {"harvest_events": 2, "total_oz": 0.0, "has_weight": False}
    ) == "no weights recorded"
    assert yearbook_mod._weight_cell(
        {"harvest_events": 1, "total_oz": 16.0, "has_weight": True}
    ) == "16.0 oz"


def test_summary_line_counts_harvest_varieties_only():
    stats = {
        "varieties": [
            {"variety": "A", "harvest_events": 2, "total_qty": 8,
             "has_weight": False},
            {"variety": "B", "harvest_events": 0, "total_qty": 0,
             "has_weight": False},
        ],
        "total_qty": 8, "total_oz": 0.0, "has_weight_any": False,
        "total_spent": 10.0,
    }
    line = yearbook_mod._summary_line(stats)
    assert "1 varieties with harvest entries" in line
    assert "no weights recorded" in line
    assert "0.0 oz harvested" not in line


def test_story_prompt_is_grounded(seeded, monkeypatch):
    prompts = []

    def fake_chat(session, messages, timeout=None):
        prompts.append(messages[0]["content"])
        return "A canned season story."

    monkeypatch.setattr(yearbook_mod.llm_mod, "chat", fake_chat)
    with Session(engine) as s:
        stats = yearbook_mod.build_yearbook_stats(s, YEAR)
        story = yearbook_mod.write_story(s, stats)
    assert story == "A canned season story."
    prompt = prompts[0]
    # Records actually reach the prompt.
    assert "White grubs (scarab beetle larvae)" in prompt
    assert "Died 2041 - under-watered through the season." in prompt
    assert "Mite stippling (unconfirmed)" in prompt
    assert "no weights recorded" in prompt
    # Grounding rules, verbatim enough to catch a regression.
    assert "state only what the records above support" in prompt
    assert "never present a missing value as zero" in prompt
    assert "Never invent a pest, a weather event, or a cause of death" in prompt
    assert "cause of death comes only from that plant's own notes" in prompt
    assert "cause is unknown" in prompt
    # And the old falsehood never appears.
    assert "0.0 oz" not in prompt


def test_pdf_renders_with_unweighed_stats(seeded):
    with Session(engine) as s:
        stats = yearbook_mod.build_yearbook_stats(s, YEAR)
    pdf = yearbook_mod.render_pdf(stats, "A story.", [])
    assert pdf[:5] == b"%PDF-"
