"""Season recap: per-variety photo timeline narrated by the vision model.

Run with:  pytest -q
"""
from __future__ import annotations

import os
import tempfile
from datetime import date as Date
from datetime import datetime
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="season-recap-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session as SQLSession, select  # noqa: E402

from app import frost as frost_mod  # noqa: E402
from app import llm as llm_mod  # noqa: E402
from app import season_recap as recap_mod  # noqa: E402
from app.database import UPLOAD_DIR, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (Album, AlbumImage, ObservationImage, ObservationLog,  # noqa: E402
                        Plant)

init_db()
client = TestClient(app)


def _settings(on: bool = True) -> None:
    with SQLSession(engine) as s:
        frost_mod.set_setting(s, "local_ai_enabled", "true" if on else "false")
        frost_mod.set_setting(s, "ai_provider", "ollama")
        frost_mod.set_setting(s, "ai_chat_enabled", "true")
        s.commit()


@pytest.fixture(autouse=True)
def _defaults():
    _settings(True)
    yield
    _settings(True)


def _photo_file(name: str) -> str:
    """Write a tiny real JPEG under the bound UPLOAD_DIR; return its /uploads path."""
    from PIL import Image

    d = UPLOAD_DIR / "albums" / "recap-test"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    Image.new("RGB", (16, 16), (90, 140, 90)).save(p, format="JPEG")
    return f"/uploads/albums/recap-test/{name}"


@pytest.fixture
def planted():
    """One plant with album photos on several dates + one observation photo."""
    _settings(True)
    with SQLSession(engine) as s:
        p = Plant(variety_name="Recap Tomato", species_type="Tomato", status="Growing")
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
        album = Album(name="recap-test-album")
        s.add(album)
        s.commit()
        s.refresh(album)
        for i, day in enumerate(["2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01"]):
            s.add(AlbumImage(
                album_id=album.id, file_path=_photo_file(f"album-{i}.jpg"),
                taken_at=datetime.fromisoformat(day), plant_id=pid,
            ))
        obs = ObservationLog(plant_id=pid, plant_name="Recap Tomato",
                             date="2026-06-15", notes="looking good", health_scale=8)
        s.add(obs)
        s.commit()
        s.refresh(obs)
        s.add(ObservationImage(observation_id=obs.id,
                               file_path=_photo_file("obs-1.jpg")))
        s.commit()
    yield pid
    with SQLSession(engine) as s:
        for row in s.exec(select(AlbumImage).where(AlbumImage.plant_id == pid)).all():
            s.delete(row)
        for row in s.exec(select(ObservationLog).where(ObservationLog.plant_id == pid)).all():
            s.delete(row)
        for row in s.exec(select(Album).where(Album.name == "recap-test-album")).all():
            s.delete(row)
        pl = s.get(Plant, pid)
        if pl:
            s.delete(pl)
        s.commit()


def _stub_narrate(monkeypatch, text="A lovely season.", error=None):
    calls = []

    def fake(session, messages, **kwargs):
        calls.append({"messages": messages, "images": kwargs.get("images")})
        if error is not None:
            raise error
        return text

    monkeypatch.setattr(llm_mod, "chat", fake)
    return calls


# --- pick_spread ------------------------------------------------------------

def _mk(days):
    return [{"file_path": f"/uploads/x/{i}.jpg",
             "date": Date.fromisoformat(d) if d else None,
             "source": "album"} for i, d in enumerate(days)]


def test_pick_spread_even_includes_first_and_last():
    days = sorted([f"2026-{m:02d}-01" for m in range(1, 13)] + [f"2026-{m:02d}-15" for m in range(1, 13)])
    photos = _mk(days)
    picked = recap_mod.pick_spread(photos)
    assert len(picked) == 8
    assert picked[0]["date"] == Date(2026, 1, 1)
    assert picked[-1]["date"] == Date(2026, 12, 15)
    dates = [p["date"] for p in picked]
    assert dates == sorted(dates)


def test_pick_spread_dedupes_same_day():
    photos = _mk(["2026-05-01", "2026-05-01", "2026-05-01", "2026-06-01"])
    picked = recap_mod.pick_spread(photos)
    assert len(picked) == 2
    assert [p["date"].isoformat() for p in picked] == ["2026-05-01", "2026-06-01"]


def test_pick_spread_few_photos_returned_as_is():
    photos = _mk(["2026-05-01", "2026-06-01"])
    assert recap_mod.pick_spread(photos) == photos
    assert recap_mod.pick_spread([]) == []


# --- build_recap / endpoint -------------------------------------------------

def test_recap_no_photos_is_graceful(planted, monkeypatch):
    calls = _stub_narrate(monkeypatch, error=AssertionError("LLM must not be called"))
    with SQLSession(engine) as s:
        lonely = Plant(variety_name="Lonely Pepper", species_type="Pepper", status="Growing")
        s.add(lonely)
        s.commit()
        s.refresh(lonely)
        out = recap_mod.build_recap(s, lonely)
        s.delete(lonely)
        s.commit()
    assert "error" in out and "No photos" in out["error"]
    assert calls == []


def test_recap_endpoint_happy_path(planted, monkeypatch):
    calls = _stub_narrate(monkeypatch, "From seedling to salsa.")
    r = client.post("/api/ai/season-recap", json={"plant_id": planted})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["narrative"] == "From seedling to salsa."
    assert body["plant"]["name"] == "Recap Tomato"
    # 4 album photos + 1 observation photo, all on distinct days -> 5 picked
    assert len(body["photos"]) == 5
    assert calls and len(calls[0]["images"]) == 5
    assert all(u.startswith("data:image/jpeg;base64,") for u in calls[0]["images"])


def test_recap_endpoint_fuzzy_name(planted, monkeypatch):
    _stub_narrate(monkeypatch, "Tasty.")
    r = client.post("/api/ai/season-recap", json={"plant": "recap tomato"})
    assert r.status_code == 200, r.text
    assert r.json()["plant"]["name"] == "Recap Tomato"


def test_recap_endpoint_unknown_plant(monkeypatch):
    _stub_narrate(monkeypatch, "x")
    r = client.post("/api/ai/season-recap", json={"plant_id": 999999})
    assert r.status_code == 404


def test_recap_endpoint_llm_error_is_graceful(planted, monkeypatch):
    _stub_narrate(monkeypatch, error=llm_mod.LLMError("vision not supported"))
    r = client.post("/api/ai/season-recap", json={"plant_id": planted})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "error" in body and "vision not supported" in body["error"]


def test_recap_endpoint_ai_off(planted, monkeypatch):
    _settings(False)
    r = client.post("/api/ai/season-recap", json={"plant_id": planted})
    assert r.status_code == 400


def test_chat_tool_season_recap(planted, monkeypatch):
    from app import ai_tools as ai_tools_mod

    _stub_narrate(monkeypatch, "What a year.")
    with SQLSession(engine) as s:
        out = ai_tools_mod.execute_read(s, "season_recap", {"plant": "recap tomatoes"})
    assert out.get("narrative") == "What a year."
    assert out["plant"]["name"] == "Recap Tomato"


def test_chat_tool_season_recap_unknown_plant(monkeypatch):
    from app import ai_tools as ai_tools_mod

    _stub_narrate(monkeypatch, error=AssertionError("LLM must not be called"))
    with SQLSession(engine) as s:
        out = ai_tools_mod.execute_read(s, "season_recap", {"plant": "moon turnips"})
    assert "error" in out
