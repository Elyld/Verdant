"""📸 Growth stall detector — ask the vision model whether a plant has visibly grown.

Gathers the plant's photos from the last ~6 weeks (Immich album matches +
observation photos), picks oldest/middle/newest, and asks the configured
vision model to judge whether growth looks stalled and suggest likely causes.

Advisory only: returns a dict (or {"error": ...}) and never raises. Photos
are only ever sent to the gardener's already-configured LLM provider via
``app.llm.chat`` — the same path the season recap uses.
"""
from __future__ import annotations

import json
from datetime import date as Date
from datetime import timedelta
from typing import Optional

from sqlmodel import Session, select

from app import llm as llm_mod
from app.models import Plant
from app.season_recap import _photo_data_uri, _real_path, plant_photos

# Only photos from this window count — the question is "has it grown LATELY".
WINDOW_DAYS = 42
# Vision request budget: oldest, middle, newest.
MAX_CHECK_PHOTOS = 3


def _match_plant_fuzzy(session: Session, name: str) -> Optional[Plant]:
    """Fuzzy plant match, same spirit as ai_tools._match_plant.

    Case-insensitive name/substring match, with a species fallback so
    "tomatoes" finds a Tomato plant.
    """
    key = (name or "").strip().lower()
    if not key:
        return None
    plants = session.exec(select(Plant)).all()
    lowered = {(p.variety_name or "").lower(): p for p in plants}
    if key in lowered:
        return lowered[key]
    hit = next(
        (p for p in plants
         if key in (p.variety_name or "").lower()
         or (p.variety_name or "").lower() in key),
        None,
    )
    if hit is not None:
        return hit
    for p in plants:
        sp = (p.species_type or "").strip().lower()
        if sp and key in (sp, sp + "s", sp + "es"):
            return p
    return None


def _recent_plant_photos(session: Session, plant: Plant) -> list[dict]:
    """The plant's photos from the last ~6 weeks, oldest first.

    Dateless photos can't anchor a timeline, so they're dropped.
    """
    cutoff = Date.today() - timedelta(days=WINDOW_DAYS)
    return [p for p in plant_photos(session, plant.id)
            if p["date"] is not None and p["date"] >= cutoff]


def _pick_timeline(photos: list[dict]) -> list[dict]:
    """Oldest, middle, newest — the spread that shows growth (or lack of it)."""
    if len(photos) <= MAX_CHECK_PHOTOS:
        return photos
    return [photos[0], photos[len(photos) // 2], photos[-1]]


def _check_prompt(plant: Plant, photos: list[dict]) -> str:
    dates = ", ".join(p["date"].isoformat() for p in photos)
    species = (plant.species_type or "").strip()
    who = f"{plant.variety_name} ({species})" if species else plant.variety_name
    return (
        f"You are Verdant, the friendly gardening-neighbor assistant inside a "
        f"gardener's personal garden journal. These {len(photos)} photos of the "
        f"same {who} plant were taken on {dates} (oldest first). "
        f"Has it visibly grown? If growth looks stalled, suggest the most likely "
        f"causes (rootbound, nutrients, light, water, pests) as a short advisory. "
        f"Only comment on what you can actually see; if a photo is unclear, say so. "
        f'Respond with JSON only: {{"verdict_summary": "one short sentence, e.g. '
        f'\\"growing steadily\\" or \\"growth looks stalled\\", with dates if useful", '
        f'"advice": "2-3 sentences: most likely cause(s) and the gentlest thing to '
        f'try first"}}.'
    )


def _parse_verdict(text: str) -> tuple[str, str]:
    """Pull verdict_summary/advice out of the model's reply. Never raises."""
    raw = (text or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                summary = str(data.get("verdict_summary") or "").strip()
                advice = str(data.get("advice") or "").strip()
                if summary or advice:
                    return summary, advice
        except (json.JSONDecodeError, TypeError):
            pass
    # Non-JSON reply (small local models often ignore the schema) — keep it
    # whole as the summary rather than losing it.
    return raw[:500], ""


def growth_check(session: Session, plant_name: str) -> dict:
    """Has this plant visibly grown over the last ~6 weeks?

    Returns {"plant", "dates", "verdict_summary", "advice"} — or {"error"}.
    Advisory only; never raises.
    """
    plant = _match_plant_fuzzy(session, plant_name)
    if plant is None:
        return {"error": f"No plant matched '{plant_name}'. Name a plant from the Plants page."}

    photos = _pick_timeline(_recent_plant_photos(session, plant))
    if len(photos) < 2:
        return {
            "error": (
                f"Not enough photos of {plant.variety_name} yet — "
                f"just {len(photos)} from the last 6 weeks. Log a couple of photos "
                "a few weeks apart and ask me again; I need at least two to compare."
            )
        }

    uris: list[str] = []
    for p in photos:
        path = _real_path(p["file_path"])
        if path is None:
            continue
        uri = _photo_data_uri(path)
        if uri:
            uris.append(uri)
    if len(uris) < 2:
        return {
            "error": (
                f"I found {len(photos)} recent photos of {plant.variety_name}, "
                "but couldn't read the image files. Nothing to compare — "
                "the files may be missing from the uploads folder."
            )
        }

    if not llm_mod.get_config(session)["enabled"]:
        return {"error": "The AI is turned off — enable it in Settings → AI and I'll take a look."}

    try:
        reply = llm_mod.chat(
            session,
            [{"role": "user", "content": _check_prompt(plant, photos)}],
            json_mode=True,
            timeout=120,
            images=uris,
        )
    except llm_mod.LLMError as e:
        return {"error": f"I couldn't get the AI to look at the photos ({e}). Check Settings → AI."}
    except Exception as e:  # never break the caller on a model hiccup
        return {"error": f"The growth check didn't come together ({e})."}

    verdict_summary, advice = _parse_verdict(reply)
    if not verdict_summary:
        return {"error": "The AI came back empty-handed — try again in a bit."}
    return {
        "plant": plant.variety_name,
        "dates": [p["date"].isoformat() for p in photos],
        "verdict_summary": verdict_summary,
        "advice": advice,
    }
