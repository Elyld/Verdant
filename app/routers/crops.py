"""Curated crop lookup — replaces the defunct OpenFarm API.

A bundled, offline crop database with the planting guidance a gardener
actually needs when adding a plant: sun, spacing, sowing depth,
germination and maturity timing, plus a short how-to. Instant, private,
no API key, no network.

v2.33.0: variety-level entries (curated popular varieties per crop, with
their own maturity timing) and seed-stash matching, so a search for
"Cherokee Purple" finds the variety — and your own seed packets.
Every result carries its source: the built-in guide or your seed stash.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, or_, select

from app import growstuff
from app.database import get_session
from app.models import SeedPacket

router = APIRouter(prefix="/api/crops", tags=["crops"])

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "crops.json"

GUIDE_SOURCE = "Built-in crop guide"
STASH_SOURCE = "Your seed stash"


@lru_cache(maxsize=1)
def _crops() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _guide_summary(crop: dict, variety: dict | None = None) -> dict:
    bundled = (variety.get("days_to_maturity") if variety else None) or crop[
        "days_to_maturity"
    ]
    # Growstuff community medians (real gardens) win over the bundled
    # packet-claim numbers when cached data is available.
    community = growstuff.get(crop.get("key", ""))
    maturity = bundled
    community_info = None
    if community:
        maturity = int(community["median_days_to_first_harvest"])
        community_info = {
            "median_days_to_first_harvest": maturity,
            "gardens": community.get("plantings_count"),
        }
    if variety:
        return {
            "kind": "variety",
            "key": crop["key"],
            "name": variety["name"],
            "crop_name": crop["name"],
            "family": crop["family"],
            "sun": crop["sun"],
            "days_to_maturity": maturity,
            "maturity_source": "community" if community_info else "guide",
            "community": community_info,
            "note": variety.get("note", ""),
        }
    return {
        "kind": "crop",
        "key": crop["key"],
        "name": crop["name"],
        "crop_name": crop["name"],
        "family": crop["family"],
        "sun": crop["sun"],
        "days_to_maturity": maturity,
        "maturity_source": "community" if community_info else "guide",
        "community": community_info,
        "note": "",
    }


def _escape_like(needle: str) -> str:
    return needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
def search_crops(q: str = "", session: Session = Depends(get_session)) -> dict:
    """Substring search over crop names, aliases, and variety names, plus the
    user's own seed packets. Empty query → empty lists."""
    needle = (q or "").strip().lower()
    if not needle:
        return {"ok": True, "guide": [], "stash": []}

    # Kick off a background Growstuff refresh when the cache is stale; the
    # search itself always serves instantly from cache/disk.
    growstuff.refresh_if_stale()

    guide: list[dict] = []
    for c in _crops():
        if needle in c["name"].lower() or any(needle in a.lower() for a in c.get("aliases", [])):
            guide.append(_guide_summary(c))
        for v in c.get("varieties", []):
            if needle in v["name"].lower():
                guide.append(_guide_summary(c, v))
    # variety/crop name matches first, then alphabetical
    guide.sort(key=lambda e: (0 if e["name"].lower().startswith(needle) else 1, e["name"]))
    guide = guide[:20]

    like = f"%{_escape_like(needle)}%"
    packets = session.exec(
        select(SeedPacket)
        .where(
            or_(
                SeedPacket.variety_name.ilike(like),
                SeedPacket.species_type.ilike(like),
                SeedPacket.category.ilike(like),
            )
        )
        .order_by(SeedPacket.variety_name)
        .limit(10)
    ).all()
    stash = [
        {
            "kind": "packet",
            "packet_id": p.id,
            "variety_name": p.variety_name,
            "species_type": p.species_type or "",
            "vendor_name": p.vendor_name or "",
            "year_acquired": p.year_acquired,
        }
        for p in packets
    ]
    return {"ok": True, "guide": guide, "stash": stash}


@router.get("/sow-by")
def sow_by(
    days_to_maturity: int, session: Session = Depends(get_session)
) -> dict:
    """Planting calculator: last safe sow date for a fall harvest.

    sow_by = next_first_frost − days_to_maturity − 14d buffer.
    Uses the annualized next frost (same as the header countdown), so crops
    like garlic — sown in fall for next year — get a sensible answer.
    """
    from datetime import date as date_cls

    from app import frost as frost_mod
    from app import planting

    today = date_cls.today()
    frost_date, source, _zone = frost_mod.resolve_frost(session, "first", today=today)
    if frost_date is None or not days_to_maturity:
        return {
            "ok": True,
            "days_to_maturity": days_to_maturity,
            "buffer_days": planting.SOW_BUFFER_DAYS,
            "frost_date": None,
            "frost_source": None,
            "sow_by": None,
            "days_left": None,
            "verdict": "no_frost_date",
        }
    sow_by_date = planting.last_safe_sow_date(frost_date, days_to_maturity)
    return {
        "ok": True,
        "days_to_maturity": days_to_maturity,
        "buffer_days": planting.SOW_BUFFER_DAYS,
        "frost_date": frost_date.isoformat(),
        "frost_source": source,
        "sow_by": sow_by_date.isoformat(),
        "days_left": (sow_by_date - today).days,
        "verdict": planting.sow_verdict(sow_by_date, today),
    }


@router.get("/{key}")
def crop_detail(key: str) -> dict:
    """Full growing info for one crop, including its varieties and source."""
    for crop in _crops():
        if crop["key"] == key:
            community = growstuff.get(crop.get("key", ""))
            detail = {**crop, "source": GUIDE_SOURCE}
            if community:
                detail["community"] = {
                    "median_days_to_first_harvest": community[
                        "median_days_to_first_harvest"
                    ],
                    "median_lifespan": community.get("median_lifespan"),
                    "gardens": community.get("plantings_count"),
                    "harvests": community.get("harvests_count"),
                }
            return {"ok": True, "crop": detail}
    raise HTTPException(404, f"Unknown crop {key!r}.")
