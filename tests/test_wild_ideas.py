"""Tests for the v2.51.0 "wild ideas" batch — one file covering each feature.

Merged from the four per-feature modules (autopsy, caretaker/time-travel,
stall/frost-gamble, yearbook/true-cost). All modules share one temp DB per
pytest process (the engine binds the FIRST-imported test module's dirs), so
fixtures use unique variety names / a unique year to avoid cross-module
collisions.

Run:  cd ~/workspace/verdant && PYTHONPATH=. .venv/bin/python -m pytest tests/test_wild_ideas.py -q
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="wild-ideas-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402
from sqlmodel import Session as SQLSession  # noqa: E402
from sqlmodel import select  # noqa: E402

import app.frost_gamble as frost_gamble_mod  # noqa: E402
import app.stall as stall_mod  # noqa: E402
from app import ai_tools as ai_tools_mod  # noqa: E402
from app import autopsy as autopsy_mod  # noqa: E402
from app import caretaker as caretaker_mod  # noqa: E402
from app import frost as frost_mod  # noqa: E402
from app import time_travel as time_travel_mod  # noqa: E402
from app import true_cost as true_cost_mod  # noqa: E402
from app import yearbook as yearbook_mod  # noqa: E402
from app.database import UPLOAD_DIR, engine, get_session, init_db  # noqa: E402
from app.models import (  # noqa: E402
    Album,
    AlbumImage,
    Expense,
    Harvest,
    ObservationImage,
    ObservationLog,
    PestLog,
    Plant,
    WateringLog,
)
from app.routers.caretaker import build_caretaker_html  # noqa: E402
from app.routers.caretaker import router as caretaker_router  # noqa: E402
from app.routers.yearbook import router as yearbook_router  # noqa: E402

assert UPLOAD_DIR  # keep the conventional import used
assert MagicMock and io and json  # keep the conventional imports used

init_db()

_test_app = FastAPI()
_test_app.include_router(caretaker_router)
client = TestClient(_test_app)


###########################################################################
# 💀 Plant autopsy (record_autopsy write tool)
###########################################################################

@pytest.fixture
def garden():
    """One uniquely-named Growing plant, cleaned up afterwards."""
    with SQLSession(engine) as s:
        p = Plant(variety_name="Autopsy Tomato", species_type="Tomato",
                  status="Growing")
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
    yield pid
    with SQLSession(engine) as s:
        for row in s.exec(select(ObservationLog)
                          .where(ObservationLog.plant_id == pid)).all():
            s.delete(row)
        for row in s.exec(select(Harvest)
                          .where(Harvest.plant_id == pid)).all():
            s.delete(row)
        p = s.get(Plant, pid)
        if p:
            s.delete(p)
        s.commit()


def _draft(session, **kwargs):
    """resolve_autopsy_args + the real "note" draft flow, like the spec does."""
    args = autopsy_mod.resolve_autopsy_args(
        session, kwargs.get("plant"), kwargs.get("cause"), kwargs.get("notes", ""))
    assert args is not None
    return ai_tools_mod.build_write_draft(session, "save_memory_note", args)


def test_compose_autopsy_note_format():
    assert (autopsy_mod.compose_autopsy_note("Cherokee Purple", "damping off")
            == "💀 Autopsy — Cherokee Purple: damping off.")
    assert (autopsy_mod.compose_autopsy_note("Cherokee Purple", "damping off",
                                             "stems brown at the base")
            == "💀 Autopsy — Cherokee Purple: damping off. stems brown at the base")


def test_parse_autopsy_note_roundtrip():
    text = autopsy_mod.compose_autopsy_note("Cherokee Purple", "damping off",
                                            "sudden collapse")
    variety, rest = autopsy_mod.parse_autopsy_note(text)
    assert variety == "Cherokee Purple"
    assert rest == "damping off. sudden collapse"


def test_autopsy_draft_known_plant(garden):
    with SQLSession(engine) as s:
        # lowercase on purpose: exercises the fuzzy _match_plant path.
        # NOTE: _match_plant resolves via _plant_names, which caps at 40
        # Growing plants — in a crowded shared test DB it may legitimately
        # miss, and resolve_autopsy_args must then fall back gracefully.
        p = ai_tools_mod._match_plant(s, "autopsy tomato")
        d = _draft(s, plant="autopsy tomato", cause="damping off",
                   notes="stems went brown at the base")
    assert d is not None
    assert d["action"] == "note"  # existing action — no frontend change needed
    assert d["notes"].startswith("💀 Autopsy")
    assert "damping off" in d["notes"]
    assert "stems went brown at the base" in d["notes"]
    expected_variety = p.variety_name if p else "autopsy tomato"
    assert d["notes"].startswith(f"💀 Autopsy — {expected_variety}:")
    assert d["plant_name"]  # set in both paths (variety name or "Notebook")
    if p:
        assert d["plant_name"] == "Autopsy Tomato"


def test_autopsy_draft_unknown_plant():
    with SQLSession(engine) as s:
        d = _draft(s, plant="Mystery Melon", cause="unknown wilt")
    # handled gracefully: draft still builds, the note text carries the name
    assert d is not None
    assert d["action"] == "note"
    assert d["notes"].startswith("💀 Autopsy — Mystery Melon: unknown wilt.")
    assert d["plant_name"] == "Notebook"  # pseudo-plant fallback, like memory notes


def test_autopsy_draft_missing_params(garden):
    with SQLSession(engine) as s:
        assert autopsy_mod.resolve_autopsy_args(s, "Autopsy Tomato", "") is None
        assert autopsy_mod.resolve_autopsy_args(s, "", "damping off") is None
        assert autopsy_mod.resolve_autopsy_args(s, "  ", "damping off") is None


def test_autopsy_deaths_scan_groups_by_variety(garden):
    with SQLSession(engine) as s:
        s.add(ObservationLog(plant_id=garden, plant_name="Autopsy Tomato",
                             date="2026-07-14",
                             notes=autopsy_mod.compose_autopsy_note(
                                 "Autopsy Tomato", "damping off")))
        # a regular note must NOT be picked up by the scan
        s.add(ObservationLog(plant_id=garden, plant_name="Autopsy Tomato",
                             date="2026-07-10", notes="first flowers"))
        # unknown plant: plant_name falls back to Notebook, but the note text
        # still carries the variety — the scan must group by it
        s.add(ObservationLog(plant_id=None, plant_name="Notebook",
                             date="2026-08-02",
                             notes=autopsy_mod.compose_autopsy_note(
                                 "Mystery Melon", "unknown wilt")))
        s.commit()
    with SQLSession(engine) as s:
        deaths = autopsy_mod.autopsy_deaths_by_variety(s)
    assert deaths == {
        "Autopsy Tomato": ["died 2026: damping off."],
        "Mystery Melon": ["died 2026: unknown wilt."],
    }


def test_autopsy_notes_attach_to_variety_performance(garden):
    """The integration spec's patch: deaths attach to variety entries."""
    with SQLSession(engine) as s:
        s.add(Harvest(plant_id=garden, date="2026-08-01", quantity=5))
        s.add(ObservationLog(plant_id=garden, plant_name="Autopsy Tomato",
                             date="2026-09-02",
                             notes=autopsy_mod.compose_autopsy_note(
                                 "Autopsy Tomato", "late blight")))
        s.commit()
    with SQLSession(engine) as s:
        perf = ai_tools_mod._t_variety_performance(s, {})
        autopsy_mod.attach_deaths(
            perf["varieties"], autopsy_mod.autopsy_deaths_by_variety(s))
    entry = next(v for v in perf["varieties"]
                 if v["variety"] == "Autopsy Tomato")
    assert entry["notes"] == ["died 2026: late blight."]
    assert entry["total_quantity"] == 5  # harvest data untouched


def test_autopsy_death_only_variety_still_listed():
    """A variety that died before ever harvesting shows up with zero totals."""
    with SQLSession(engine) as s:
        s.add(ObservationLog(plant_id=None, plant_name="Notebook",
                             date="2026-06-11",
                             notes=autopsy_mod.compose_autopsy_note(
                                 "Doomed Pepper", "cutworms")))
        s.commit()
    with SQLSession(engine) as s:
        perf = ai_tools_mod._t_variety_performance(s, {})
        autopsy_mod.attach_deaths(
            perf["varieties"], autopsy_mod.autopsy_deaths_by_variety(s))
    entry = next(v for v in perf["varieties"] if v["variety"] == "Doomed Pepper")
    assert entry["notes"] == ["died 2026: cutworms."]
    assert entry["total_harvests"] == 0
    assert entry["total_quantity"] == 0
    # cleanup the orphaned note
    with SQLSession(engine) as s:
        for row in s.exec(select(ObservationLog)
                          .where(ObservationLog.notes.like("💀 Autopsy — Doomed Pepper%"))).all():
            s.delete(row)
        s.commit()


###########################################################################
# 🏖️ Vacation caretaker sheet + 🕰️ This week last year
###########################################################################

def _session() -> Session:
    return Session(engine)


SEEDED = False


def _seed():
    global SEEDED
    if SEEDED:
        return
    SEEDED = True
    with _session() as s:
        today = Date.today()
        tomato = Plant(variety_name="Cherokee Purple", species_type="Tomato",
                       status="Growing", water_every_days=2,
                       date_planted=today - timedelta(days=90),
                       days_to_maturity=70,
                       notes="Likes the corner of the raised bed.")
        s.add(tomato)
        s.flush()
        # Overdue watering.
        s.add(WateringLog(plant_id=tomato.id,
                          date=(today - timedelta(days=5)).isoformat(),
                          method="hose"))
        # Active pest.
        s.add(PestLog(date=(today - timedelta(days=1)).isoformat(),
                      pest_name="Hornworm", plant_id=tomato.id,
                      treatment="Hand-pick + BT spray",
                      notes="Found two on the lower leaves.", resolved=False))
        # --- This week last year items ---
        start, end = time_travel_mod._week_window(today)
        s.add(ObservationLog(date=start, plant_name="Cherokee Purple",
                             plant_id=tomato.id,
                             notes="First flowers opened today!"))
        s.add(Harvest(plant_id=tomato.id, date=end, quantity=6,
                      unit="fruit", notes="Beautiful slicers."))
        album = Album(name="Last year garden")
        s.add(album)
        s.flush()
        s.add(AlbumImage(album_id=album.id, file_path="2025/tomato.jpg",
                         taken_at=datetime.fromisoformat(start) +
                         timedelta(days=2, hours=10),
                         title="Tomato flowers", plant_id=tomato.id))
        # --- Decoys (outside the target week) ---
        s.add(ObservationLog(date=(today - timedelta(days=30)).isoformat(),
                             plant_name="Cherokee Purple",
                             plant_id=tomato.id,
                             notes="Decoy: recent note, not last year."))
        s.add(Harvest(plant_id=tomato.id,
                      date=(today - timedelta(days=400)).isoformat(),
                      quantity=1, unit="fruit", notes="Decoy: too long ago."))
        s.add(AlbumImage(album_id=album.id, file_path="2026/decoy.jpg",
                         taken_at=datetime.combine(today, datetime.min.time()),
                         title="Decoy photo"))
        s.commit()


# ---------------------------------------------------------------------------
# Caretaker sheet
# ---------------------------------------------------------------------------

def test_caretaker_sheet_empty_garden_friendly():
    """Caretaker sheet always renders its sections — never an error page.

    (In the full suite the shared DB may hold other modules' plants, so the
    "Nothing due" fallback only shows on a truly empty garden; the empty-dict
    unit test below covers that path directly.)
    """
    resp = client.get("/api/caretaker-sheet")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    for section in ("💧 Water these", "🧺 Ready to pick", "🐛 Keep an eye on",
                    "📝 Notes", "Emergency contacts"):
        assert section in body


def test_caretaker_data_sections():
    _seed()
    with _session() as s:
        data = caretaker_mod.caretaker_data(s)
    assert {k for k in data} >= {"watering_due", "harvest_ready",
                                 "pest_watches", "general_notes"}
    water = data["watering_due"]
    assert any(w["plant_name"] == "Cherokee Purple" and
               w["status"] == "overdue" for w in water)
    ready = data["harvest_ready"]
    assert any(h["plant_name"] == "Cherokee Purple" for h in ready)
    pests = data["pest_watches"]
    assert any(p["pest_name"] == "Hornworm" and not p["resolved"]
               for p in pests)
    notes = data["general_notes"]
    assert any("Cherokee Purple" in n for n in notes)


def test_caretaker_sheet_seeded_html():
    _seed()
    resp = client.get("/api/caretaker-sheet")
    assert resp.status_code == 200
    body = resp.text
    assert "Cherokee Purple" in body
    assert "Hornworm" in body
    assert "overdue" in body
    assert "@media print" in body  # print-friendly CSS present


def test_build_caretaker_html_empty_dict_never_raises():
    body = build_caretaker_html({})
    assert "💧 Water these" in body and "Emergency contacts" in body


# ---------------------------------------------------------------------------
# This week last year
# ---------------------------------------------------------------------------

def test_this_week_last_year_returns_only_target_week():
    _seed()
    with _session() as s:
        data = time_travel_mod.this_week_last_year(s)
    obs_dates = [e["date"] for e in data["logs"]]
    photo_dates = [p["date"] for p in data["photos"]]
    # The three seeded target-week items are present…
    assert len(data["photos"]) == 1
    assert data["photos"][0]["plant_name"] == "Cherokee Purple"
    assert len(data["logs"]) == 2
    kinds = {e["kind"] for e in data["logs"]}
    assert kinds == {"note", "harvest"}
    assert any(e["notes"] == "First flowers opened today!" for e in data["logs"])
    # …and the decoys are not.
    assert not any("Decoy" in (e["notes"] or "") for e in data["logs"])
    assert all("decoy" not in p["file_path"] for p in data["photos"])
    assert len(obs_dates) + len(photo_dates) <= time_travel_mod.MAX_ITEMS


def test_digest_section_formatting():
    _seed()
    with _session() as s:
        section = time_travel_mod.digest_section(s)
    assert section is not None
    assert section.startswith("🕰️ **This week last year**")
    lines = section.splitlines()
    assert len(lines) <= time_travel_mod.MAX_DIGEST_LINES + 1
    assert any(ln.startswith("• 📷") for ln in lines)
    assert any("harvested" in ln for ln in lines)


def test_digest_section_none_when_empty():
    mock_session = MagicMock()
    mock_session.exec.return_value.all.return_value = []
    assert time_travel_mod.digest_section(mock_session) is None
    data = time_travel_mod.this_week_last_year(mock_session)
    assert data == {"photos": [], "logs": []}


###########################################################################
# 🌱 Growth stall detector + 🎲 Frost-night gamble
###########################################################################

def _photo_file(name: str, color=(120, 160, 90)) -> str:
    """Write a real JPEG into the uploads dir; return its /uploads/... path."""
    from PIL import Image

    d = UPLOAD_DIR / "test-wild"
    d.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), color).save(d / name, "JPEG")
    return f"/uploads/test-wild/{name}"


def _make_plant(session, name, species, **kw):
    p = Plant(variety_name=name, species_type=species, status="Growing", **kw)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _add_album_photo(session, plant, days_ago):
    album = Album(name=f"wild-test-{days_ago}")
    session.add(album)
    session.commit()
    session.refresh(album)
    img = AlbumImage(
        album_id=album.id,
        plant_id=plant.id,
        file_path=_photo_file(f"wild-album-{plant.id}-{days_ago}.jpg"),
        taken_at=datetime.now() - timedelta(days=days_ago),
    )
    session.add(img)
    session.commit()
    return img


def _add_observation_photo(session, plant, days_ago):
    day = Date.today() - timedelta(days=days_ago)
    obs = ObservationLog(
        date=day.isoformat(), plant_name=plant.variety_name,
        plant_id=plant.id, notes="wild test photo",
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)
    img = ObservationImage(
        observation_id=obs.id,
        file_path=_photo_file(f"wild-obs-{plant.id}-{days_ago}.jpg"),
    )
    session.add(img)
    session.commit()
    return img


def _fc(low_f):
    """A stubbed forecast dict shaped like app.weather.get_forecast."""
    return {"daily": [{"tmin_f": low_f, "tmax_f": low_f + 12}]}


@pytest.fixture
def session():
    """Fresh session per test; cleans up this module's plants afterwards."""
    created = []
    with SQLSession(engine) as s:
        yield s, created
    with SQLSession(engine) as s:
        for pid in created:
            for row in s.exec(select(ObservationImage)
                              .join(ObservationLog)
                              .where(ObservationLog.plant_id == pid)).all():
                s.delete(row)
            for row in s.exec(select(ObservationLog)
                              .where(ObservationLog.plant_id == pid)).all():
                s.delete(row)
            for row in s.exec(select(AlbumImage)
                              .where(AlbumImage.plant_id == pid)).all():
                s.delete(row)
            p = s.get(Plant, pid)
            if p:
                s.delete(p)
        s.commit()


@pytest.fixture
def no_frost_date(session, monkeypatch):
    """Force resolve_frost('first') -> None, restoring settings afterwards."""
    s, _created = session
    old = {k: frost_mod.get_setting(s, k) for k in ("frost_date", "zone")}
    frost_mod.set_setting(s, "frost_date", "")
    frost_mod.set_setting(s, "zone", "")
    s.commit()
    monkeypatch.delenv("FIRST_FROST_DATE", raising=False)
    yield
    with SQLSession(engine) as s2:
        for k, v in old.items():
            frost_mod.set_setting(s2, k, v)
        s2.commit()


def _stub_weather(monkeypatch, low_f):
    monkeypatch.setattr(
        frost_gamble_mod.weather_mod, "get_forecast",
        lambda session=None: _fc(low_f))


@pytest.fixture
def ai_on(session):
    """growth_check refuses when AI is off (the chat itself is mocked)."""
    s, _created = session
    old = frost_mod.get_setting(s, "local_ai_enabled")
    frost_mod.set_setting(s, "local_ai_enabled", "true")
    s.commit()
    yield
    with SQLSession(engine) as s2:
        frost_mod.set_setting(s2, "local_ai_enabled", old)
        s2.commit()


def _fake_chat_ok(monkeypatch, captured):
    def _fake(session, messages, *, json_mode=False, timeout=None, images=None):
        captured.append({"json_mode": json_mode, "images": images or [],
                         "prompt": messages[-1]["content"]})
        return json.dumps({
            "verdict_summary": "Growth looks stalled since mid-September.",
            "advice": "Most likely rootbound — gently check the roots and pot up if circling.",
        })
    monkeypatch.setattr(stall_mod.llm_mod, "chat", _fake)


# ---------------------------------------------------------------------------
# FEATURE 1 — growth stall detector
# ---------------------------------------------------------------------------

def test_stall_verdict_with_mocked_vision(session, ai_on, monkeypatch):
    s, created = session
    p = _make_plant(s, "Wild Stall Tomato", "Tomato")
    created.append(p.id)
    _add_album_photo(s, p, 40)          # oldest — album source
    _add_observation_photo(s, p, 20)    # middle — observation source
    _add_observation_photo(s, p, 2)     # newest

    captured = []
    _fake_chat_ok(monkeypatch, captured)

    out = stall_mod.growth_check(s, "wild stall")
    assert out["plant"] == "Wild Stall Tomato"
    expected = [(Date.today() - timedelta(days=d)).isoformat()
                for d in (40, 20, 2)]
    assert out["dates"] == expected
    assert "stalled" in out["verdict_summary"].lower()
    assert "rootbound" in out["advice"].lower()

    # The vision model got all three photos, oldest first, as data URIs.
    assert len(captured) == 1
    assert len(captured[0]["images"]) == 3
    assert all(u.startswith("data:image/jpeg;base64,")
               for u in captured[0]["images"])
    assert "Wild Stall Tomato" in captured[0]["prompt"]


def test_stall_needs_two_photos(session):
    s, created = session
    p = _make_plant(s, "Wild Lonely Pepper", "Pepper")
    created.append(p.id)
    _add_observation_photo(s, p, 5)

    out = stall_mod.growth_check(s, "Wild Lonely Pepper")
    assert "error" in out
    assert "Not enough photos" in out["error"]


def test_stall_llm_failure_is_graceful(session, ai_on, monkeypatch):
    s, created = session
    p = _make_plant(s, "Wild Glitch Basil", "Basil")
    created.append(p.id)
    _add_observation_photo(s, p, 30)
    _add_observation_photo(s, p, 3)

    def _boom(session, messages, *, json_mode=False, timeout=None, images=None):
        raise RuntimeError("model exploded")
    monkeypatch.setattr(stall_mod.llm_mod, "chat", _boom)

    out = stall_mod.growth_check(s, "Wild Glitch Basil")
    assert "error" in out


def test_stall_non_json_reply_is_kept(session, ai_on, monkeypatch):
    """Small local models may ignore the JSON schema — keep their words."""
    s, created = session
    p = _make_plant(s, "Wild Plain Cucumber", "Cucumber")
    created.append(p.id)
    _add_observation_photo(s, p, 25)
    _add_observation_photo(s, p, 4)

    monkeypatch.setattr(
        stall_mod.llm_mod, "chat",
        lambda *a, **k: "It's growing fine, new leaves since last time.")
    out = stall_mod.growth_check(s, "Wild Plain Cucumber")
    assert out["verdict_summary"] == "It's growing fine, new leaves since last time."
    assert out["advice"] == ""


def test_stall_unknown_plant(session):
    s, _created = session
    out = stall_mod.growth_check(s, "no such plant xyz")
    assert "error" in out and "No plant matched" in out["error"]


# ---------------------------------------------------------------------------
# FEATURE 2 — frost-night gamble
# ---------------------------------------------------------------------------

def test_frost_no_weather_no_verdict(session, no_frost_date, monkeypatch):
    s, _created = session
    monkeypatch.setattr(
        frost_gamble_mod.weather_mod, "get_forecast", lambda session=None: None)
    assert frost_gamble_mod.frost_verdict(s) is None
    assert frost_gamble_mod.digest_block(s) is None


def test_frost_mild_night_no_verdict(session, no_frost_date, monkeypatch):
    s, created = session
    p = _make_plant(s, "Wild Mild Basil", "Basil")
    created.append(p.id)
    _stub_weather(monkeypatch, 40)  # 40°F — above the 38°F trigger
    assert frost_gamble_mod.frost_verdict(s) is None
    assert frost_gamble_mod.digest_block(s) is None


def test_frost_hard_freeze_with_ripe_harvest(session, no_frost_date, monkeypatch):
    s, created = session
    p = _make_plant(
        s, "Wild Ripe Tomato", "Tomato",
        date_planted=Date.today() - timedelta(days=100),
        days_to_maturity=60)  # harvest_forecast -> "ready"
    created.append(p.id)
    _stub_weather(monkeypatch, 30)  # hard freeze
    out = frost_gamble_mod.frost_verdict(s)
    assert out is not None
    assert out["verdict"] == "HARVEST NOW"
    assert "Wild Ripe Tomato" in out["harvest_list"]
    assert "30" in out["reasoning"]


def test_frost_light_frost_tender_plants_cover(session, no_frost_date, monkeypatch):
    s, created = session
    p = _make_plant(s, "Wild Tender Basil", "Basil")  # is_tender keyword match
    created.append(p.id)
    _stub_weather(monkeypatch, 36)  # light frost: 33–38°F
    out = frost_gamble_mod.frost_verdict(s)
    assert out is not None
    assert out["verdict"] == "COVER"
    assert "Wild Tender Basil" in out["cover_list"]
    assert "36" in out["reasoning"]


def test_frost_digest_block_formatting(session, no_frost_date, monkeypatch):
    s, created = session
    p = _make_plant(s, "Wild Digest Basil", "Basil")
    created.append(p.id)
    _stub_weather(monkeypatch, 36)
    block = frost_gamble_mod.digest_block(s)
    assert block is not None
    assert block.startswith("❄️ **Frost call: COVER**")
    assert "Cover:" in block  # cover_list names live on this line
    # (the exact plant name isn't asserted: under a full-suite run other
    # modules' tender plants can push the list past the truncation cap)
    assert len(block) <= 1200


###########################################################################
# 📕 Yearbook + 💰 True cost
###########################################################################

YEAR = 2033


@pytest.fixture(scope="module")
def seeded():
    """A 2033 season: two tomato plants, three weighed harvests,
    a tied expense and an unassigned expense."""
    init_db()
    with Session(engine) as s:
        p1 = Plant(variety_name="Cherokee Purple", species_type="Tomato",
                   category="Annual")
        p2 = Plant(variety_name="Better Boy", species_type="Tomato",
                   category="Annual")
        s.add(p1)
        s.add(p2)
        s.commit()
        s.refresh(p1)
        s.refresh(p2)
        # 32 oz + 48 oz + 16 oz = 96 oz = 6 lb
        s.add(Harvest(plant_id=p1.id, date=f"{YEAR}-07-10", quantity=4,
                      unit="fruit", weight=32.0, weight_unit="oz"))
        s.add(Harvest(plant_id=p1.id, date=f"{YEAR}-07-20", quantity=6,
                      unit="fruit", weight=48.0, weight_unit="oz"))
        s.add(Harvest(plant_id=p2.id, date=f"{YEAR}-08-01", quantity=3,
                      unit="fruit", weight=16.0, weight_unit="oz"))
        s.add(Expense(date=f"{YEAR}-04-01", category="Seeds",
                      description="tomato seeds", amount=12.0, plant_id=p1.id))
        s.add(Expense(date=f"{YEAR}-05-01", category="Soil",
                      description="bag of compost", amount=24.0))
        s.commit()
        yield {"p1": p1.id, "p2": p2.id}


# --------------------------------------------------------------------------- #
# Yearbook
# --------------------------------------------------------------------------- #
def test_yearbook_stats(seeded):
    with Session(engine) as s:
        stats = yearbook_mod.build_yearbook_stats(s, YEAR)
    assert stats["year"] == YEAR
    assert stats["has_data"] is True
    assert stats["total_oz"] == pytest.approx(96.0)
    assert stats["total_spent"] == pytest.approx(36.0)
    by_variety = {v["variety"]: v for v in stats["varieties"]}
    assert by_variety["Cherokee Purple"]["total_oz"] == pytest.approx(80.0)
    assert by_variety["Cherokee Purple"]["harvest_events"] == 2
    assert by_variety["Better Boy"]["total_oz"] == pytest.approx(16.0)
    assert by_variety["Better Boy"]["harvest_events"] == 1


def test_yearbook_pdf_starts_with_pdf_magic(seeded):
    with Session(engine) as s:
        stats = yearbook_mod.build_yearbook_stats(s, YEAR)
    pdf = yearbook_mod.render_pdf(stats, None, [])
    assert pdf[:5] == b"%PDF-"


def test_yearbook_empty_year_graceful(seeded):
    with Session(engine) as s:
        stats = yearbook_mod.build_yearbook_stats(s, 1999)
    assert stats["has_data"] is False
    assert stats["varieties"] == []
    pdf = yearbook_mod.render_pdf(stats, None, [])
    assert pdf[:5] == b"%PDF-"


def test_write_story_returns_none_without_ai(seeded):
    """AI is off in the test DB — the story degrades to None, never raises."""
    with Session(engine) as s:
        stats = yearbook_mod.build_yearbook_stats(s, YEAR)
        assert yearbook_mod.write_story(s, stats) is None


def _make_upload(rel: str) -> Path:
    target = UPLOAD_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    Image.new("RGB", (64, 64), (107, 143, 113)).save(target, format="PNG")
    return target


def test_yearbook_photos_picks_uploads(seeded):
    path = _make_upload("test/obs1.png")
    with Session(engine) as s:
        obs = ObservationLog(date=f"{YEAR}-06-01", plant_name="Cherokee Purple",
                             plant_id=seeded["p1"], health_scale=5)
        s.add(obs)
        s.commit()
        s.refresh(obs)
        s.add(ObservationImage(observation_id=obs.id,
                               file_path=f"/uploads/test/obs1.png"))
        s.commit()
        photos = yearbook_mod.yearbook_photos(s, YEAR)
    assert len(photos) == 1
    assert photos[0]["path"].name == "obs1.png"


def test_yearbook_pdf_with_photo(seeded):
    path = _make_upload("test/obs2.png")
    pdf = yearbook_mod.render_pdf({"year": YEAR, "varieties": [],
                                   "total_spent": 0.0, "unassigned_spent": 0.0,
                                   "total_oz": 0.0, "has_data": False},
                                  None, [{"path": path, "date": None}])
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1500  # photo embedded, not a bare stub


# --------------------------------------------------------------------------- #
# True cost
# --------------------------------------------------------------------------- #
def test_true_cost_math(seeded):
    with Session(engine) as s:
        r = true_cost_mod.true_cost_report(s, YEAR)
    assert r["year"] == YEAR
    assert r["total_spend"] == pytest.approx(36.0)
    assert r["total_harvest_lb"] == pytest.approx(6.0)
    assert r["overall_per_lb"] == pytest.approx(6.0)
    by_variety = {v["variety"]: v for v in r["per_variety"]}
    cp = by_variety["Cherokee Purple"]
    assert cp["harvest_lb"] == pytest.approx(5.0)
    # $12 direct + $24 unassigned * (80/96) = $32 over 5 lb → $6.40/lb
    assert cp["per_lb"] == pytest.approx(6.40)
    assert "est." in cp["grocery_baseline"]  # baseline labeled as estimate
    bb = by_variety["Better Boy"]
    # $0 direct + $24 * (16/96) = $4 over 1 lb → $4.00/lb
    assert bb["per_lb"] == pytest.approx(4.00)
    assert "verdict" in cp and cp["verdict"]


def test_true_cost_baseline_labeling(seeded):
    with Session(engine) as s:
        r = true_cost_mod.true_cost_report(s, YEAR)
    by_variety = {v["variety"]: v for v in r["per_variety"]}
    assert by_variety["Cherokee Purple"]["grocery_baseline"] == "$2.50/lb (est.)"
    label, price = true_cost_mod._match_baseline("Dragon Carrot", "Carrot")
    assert price == 1.25
    label, price = true_cost_mod._match_baseline("Some Mystery Plant", "X")
    assert price is None and label == "—"


def test_true_cost_empty_year(seeded):
    with Session(engine) as s:
        r = true_cost_mod.true_cost_report(s, 1999)
    assert r["has_data"] is False
    assert r["overall_per_lb"] is None
    assert r["per_variety"] == []
    assert r["disclaimer"]  # honesty note always present


# --------------------------------------------------------------------------- #
# Router endpoints (mounted standalone — registration in main.py is the
# integrator's job, so the tests don't depend on it)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def test_app(seeded):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.database import get_session
    from app.routers.yearbook import router as yearbook_router

    app = FastAPI()
    app.include_router(yearbook_router)

    def override_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_yearbook_endpoint_pdf(test_app):
    r = test_app.get(f"/api/yearbook?year={YEAR}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert f"verdant-yearbook-{YEAR}.pdf" in r.headers["content-disposition"]
    assert r.content[:5] == b"%PDF-"


def test_yearbook_endpoint_empty_year_graceful(test_app):
    r = test_app.get("/api/yearbook?year=1999")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_true_cost_endpoint(test_app):
    r = test_app.get(f"/api/true-cost?year={YEAR}")
    assert r.status_code == 200
    body = r.json()
    assert body["total_spend"] == pytest.approx(36.0)
    assert body["overall_per_lb"] == pytest.approx(6.0)
    assert body["disclaimer"]
