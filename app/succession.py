"""Succession planting suggestions.

Answers: "this container is empty — what can I still plant that will
mature before the first frost?" Uses the planner's containers + plantings,
the crop guide's days-to-maturity, and the resolved first-frost date.
Rotation-aware: crops in the same family as the container's last crop are
skipped (the planner already warns about those).
"""
from __future__ import annotations

import json
import re
from datetime import date as date_cls
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "crops.json"

# Slack between expected maturity and first frost — fall growth is slower
# than the packet claims, and frost dates are estimates, not promises.
BUFFER_DAYS = 14
MAX_SUGGESTIONS = 5

# Sprouts & microgreens are indoor-tray crops, not succession plantings —
# suggesting them for a grow bag would be silly.
NON_FIELD_CROPS = ("microgreen", "sprout")


@lru_cache(maxsize=1)
def _crops() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def match_crop(text: str) -> dict | None:
    """Match a plant variety/species name to a crop-guide entry. Longest match wins."""
    t = (text or "").lower().strip()
    if not t:
        return None
    best: tuple[str, dict] | None = None
    for crop in _crops():
        names = [crop.get("name", ""), crop.get("key", "")] + list(crop.get("aliases") or [])
        # Named varieties live nested under their crop (e.g. "Cherokee Purple"
        # under tomato) — match those too.
        for v in crop.get("varieties") or []:
            names.append(v.get("name", ""))
        for n in names:
            n = (n or "").lower().strip()
            if n and n in t and (best is None or len(n) > len(best[0])):
                best = (n, crop)
    return best[1] if best else None


def _crop_family(text: str) -> str | None:
    crop = match_crop(text)
    return (crop or {}).get("family") or None


_BASE_FAMILIES: list[tuple[str, str]] | None = None


def _base_families() -> list[tuple[str, str]]:
    """(name, family) for the crop-guide entries that carry a family.

    Only ~30 of the 8k entries have one, but they're the base crops
    ("Tomato" -> Nightshade, "Bean (Pole)" -> Legume), so variety entries
    can resolve their family through them by name.
    """
    global _BASE_FAMILIES
    if _BASE_FAMILIES is None:
        pairs = []
        for crop in _crops():
            fam = (crop.get("family") or "").strip()
            name = (crop.get("name") or "").lower().strip()
            if fam and name:
                pairs.append((name, fam))
        _BASE_FAMILIES = pairs
    return _BASE_FAMILIES


def _candidate_family(crop: dict) -> str | None:
    """Family for a succession candidate, resolved via base-crop names.

    Most variety entries (e.g. "Sun Gold Pole Cherry Tomato") have a blank
    family field; matching them against the base crops ("Tomato" ->
    Nightshade) keeps rotation filtering honest.
    """
    fam = (crop.get("family") or "").strip()
    if fam:
        return fam
    name = (crop.get("name") or "").lower()
    if not name:
        return None
    best: tuple[str, str] | None = None
    for base, f in _base_families():
        if base in name and (best is None or len(base) > len(best[0])):
            best = (base, f)
    if best:
        return best[1]
    # Keyword fallback for names like "Blue Lake Pole Bean"
    # (base entry is "Bean (Pole)").
    for base, f in _base_families():
        words = sorted(
            (w for w in re.split(r"[^a-z]+", base) if len(w) >= 4),
            key=len,
            reverse=True,
        )
        for w in words:
            if w in name:
                return f
    return None


def suggestions(
    session,
    year: int | None = None,
    today: date_cls | None = None,
    first_frost: date_cls | None = None,
) -> dict:
    """Succession suggestions for every currently-free container.

    first_frost may be passed explicitly (tests, previews); otherwise it is
    resolved from settings like the rest of the app.
    """
    from app import frost as frost_mod
    from app.models import Container, Planting

    today = today or date_cls.today()
    year = year or today.year
    if first_frost is None:
        first_frost, _source, _zone = frost_mod.resolve_frost(session, "first", today=today)

    days_left = (first_frost - today).days if first_frost else None
    containers_out: list[dict] = []

    containers = (
        session.query(Container).filter(Container.season_year == year).order_by(Container.name).all()
    )
    for container in containers:
        plantings = (
            session.query(Planting)
            .filter(Planting.container_id == container.id, Planting.season_year == year)
            .all()
        )
        plants = [pl.plant for pl in plantings if pl.plant is not None]
        free = not plants or all((p.status or "") != "Growing" for p in plants)
        if not free:
            continue
        last_families = {
            fam
            for p in plants
            for fam in [_crop_family(p.variety_name), _crop_family(p.species_type or "")]
            if fam
        }
        entry: dict = {
            "container_id": container.id,
            "container_name": container.name,
            "kind": container.kind or "",
            "last_families": sorted(last_families),
            "suggestions": [],
            "note": "",
        }
        if first_frost is None:
            entry["note"] = "Set your location or frost date in Settings to get succession ideas."
        elif days_left is not None and days_left <= 0:
            entry["note"] = "First frost has passed — put this one to bed until spring. ❄️"
        else:
            cands: list[dict] = []
            assert first_frost is not None
            for crop in _crops():
                dtm = crop.get("days_to_maturity")
                if not isinstance(dtm, int) or dtm <= 0:
                    continue
                name_l = (crop.get("name") or "").lower()
                if any(tag in name_l for tag in NON_FIELD_CROPS):
                    continue
                sow_by = first_frost - timedelta(days=dtm + BUFFER_DAYS)
                if sow_by < today:
                    continue
                family = _candidate_family(crop) or ""
                if family and family in last_families:
                    continue  # rotation: same family just grew here
                cands.append(
                    {
                        "key": crop.get("key", ""),
                        "name": crop.get("name", ""),
                        "family": family,
                        "days_to_maturity": dtm,
                        "sow_by": sow_by.isoformat(),
                        "harvest_by": (first_frost - timedelta(days=BUFFER_DAYS)).isoformat(),
                    }
                )
            cands.sort(key=lambda c: c["sow_by"])
            entry["suggestions"] = cands[:MAX_SUGGESTIONS]
            if not entry["suggestions"]:
                if today.month == 10:
                    entry["note"] = "Nothing beats the frost now — 🧄 garlic goes in late October."
                elif days_left is not None and days_left < 45:
                    entry["note"] = "Too late for a full crop — consider a cover crop or overwintering garlic. 🧄"
        containers_out.append(entry)

    return {
        "ok": True,
        "year": year,
        "as_of": today.isoformat(),
        "first_frost": first_frost.isoformat() if first_frost else None,
        "days_left": days_left,
        "free_containers": len(containers_out),
        "containers": containers_out,
    }
