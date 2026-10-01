"""Per-variety photo season recap.

Gathers one plant's photos across the season — Immich album matches plus
observation photos — picks up to 8 spread across the season, and asks the
configured vision-capable chat model to narrate the season's story:
germination/growth milestones, health observations, harvest moments.

Read-only: photos are only ever sent to the gardener's already-configured
LLM provider — the same one the chat's photo-vision feature uses. Nothing
is saved unless the gardener explicitly confirms a note.
"""
from __future__ import annotations

import base64
import io
import mimetypes
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app import llm as llm_mod
from app.database import UPLOAD_DIR
from app.models import AlbumImage, ObservationImage, ObservationLog, Plant

MAX_RECAP_PHOTOS = 8
# Downscale recap photos so 8 of them fit comfortably in one vision request.
MAX_SIDE_PX = 1024


def _real_path(file_path: str) -> Optional[Path]:
    """Map a ``/uploads/...`` file_path to its real on-disk path."""
    fp = (file_path or "").strip()
    if not fp.startswith("/uploads/"):
        return None
    p = UPLOAD_DIR / fp[len("/uploads/"):]
    try:
        # Stay inside the uploads dir.
        p.resolve().relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def _parse_day(value) -> Optional[Date]:
    if not value:
        return None
    if isinstance(value, Date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return Date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def plant_photos(session: Session, plant_id: int) -> list[dict]:
    """Every photo tied to a plant, oldest first: Immich album matches plus
    observation photos. Each entry: {file_path, date, source}."""
    photos: list[dict] = []

    for img in session.exec(
        select(AlbumImage)
        .where(AlbumImage.plant_id == plant_id)
        .order_by(AlbumImage.taken_at, AlbumImage.id)
    ).all():
        if not _real_path(img.file_path):
            continue
        day = _parse_day(img.taken_at) or _parse_day(img.imported_at)
        photos.append({"file_path": img.file_path, "date": day, "source": "album"})

    for obs in session.exec(
        select(ObservationLog)
        .where(ObservationLog.plant_id == plant_id)
        .order_by(ObservationLog.date, ObservationLog.id)
    ).all():
        day = _parse_day(obs.date)
        for img in obs.images or []:
            if not _real_path(img.file_path):
                continue
            photos.append({"file_path": img.file_path, "date": day, "source": "observation"})

    photos.sort(key=lambda p: (p["date"] is None, p["date"] or Date.min, p["file_path"]))
    return photos


def pick_spread(photos: list[dict], n: int = MAX_RECAP_PHOTOS) -> list[dict]:
    """Pick up to ``n`` photos spread across the season.

    One photo per calendar day (first of the day wins), then evenly spaced
    picks that always include the first and last photo.
    """
    if not photos:
        return []
    # Dedupe near-identical dates: keep the first photo of each day.
    seen: set = set()
    deduped: list[dict] = []
    for p in photos:
        key = p["date"].isoformat() if p["date"] else f"nodate-{p['file_path']}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    if len(deduped) <= n:
        return deduped
    # Evenly spaced indices, always including first and last.
    idxs = sorted({round(i * (len(deduped) - 1) / (n - 1)) for i in range(n)})
    return [deduped[i] for i in idxs]


def _photo_data_uri(path: Path) -> Optional[str]:
    """Downscaled JPEG data URI for a photo file, or None when unreadable."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


def _recap_prompt(plant: Plant, photos: list[dict]) -> str:
    dates = ", ".join(p["date"].isoformat() if p["date"] else "date unknown" for p in photos)
    variety = plant.variety_name
    species = (plant.species_type or "").strip()
    who = f"{variety} ({species})" if species else variety
    return (
        f"You are Verdant, the friendly gardening-neighbor assistant inside a gardener's "
        f"personal garden journal. The gardener has shared {len(photos)} photos of their "
        f"{who} plant, taken across the season on these dates (in photo order): {dates}.\n\n"
        f"Narrate this plant's season as a warm, short story — a few paragraphs. Cover: "
        f"how it started, growth milestones you can actually see, health observations "
        f"(pests, stress, thriving), and harvest moments if any are visible. "
        f"Be specific about what you see in the photos; never invent dates, events, or "
        f"details that aren't visible. If a photo is unclear, say so briefly. "
        f"No markdown tables; short paragraphs are fine."
    )


def narrate_season(session: Session, plant: Plant, photos: list[dict]) -> dict:
    """Send the photos to the configured vision model and get the story.

    Returns {"narrative": str} or {"error": str} — never raises.
    """
    uris: list[str] = []
    for p in photos:
        path = _real_path(p["file_path"])
        if path is None:
            continue
        uri = _photo_data_uri(path)
        if uri:
            uris.append(uri)
    if not uris:
        return {"error": "I couldn't read any of this plant's photo files, so there's nothing to narrate."}
    try:
        narrative = llm_mod.chat(
            session,
            [{"role": "user", "content": _recap_prompt(plant, photos)}],
            images=uris,
            timeout=120,
        )
    except llm_mod.LLMError as e:
        return {"error": f"I couldn't get the AI to look at the photos ({e}). Check Settings → AI."}
    except Exception as e:  # never break the caller on a model hiccup
        return {"error": f"The season recap didn't come together ({e})."}
    narrative = (narrative or "").strip()
    if not narrative:
        return {"error": "The AI came back empty-handed — try again in a bit."}
    return {"narrative": narrative}


def build_recap(session: Session, plant: Plant) -> dict:
    """Full recap payload for a plant, or {"error": ...} — never raises."""
    photos = plant_photos(session, plant.id)
    if not photos:
        return {
            "error": (
                f"No photos found for {plant.variety_name}. Match some photos to this "
                f"plant on the /match page (or log an observation with a photo) and "
                f"try again."
            )
        }
    picked = pick_spread(photos)
    result = narrate_season(session, plant, picked)
    if "error" in result:
        return result
    return {
        "plant": {"id": plant.id, "name": plant.variety_name,
                  "species": plant.species_type or ""},
        "photos": [
            {"file_path": p["file_path"],
             "date": p["date"].isoformat() if p["date"] else None}
            for p in picked
        ],
        "narrative": result["narrative"],
    }
