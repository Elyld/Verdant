"""Curated crop lookup — replaces the defunct OpenFarm API.

A bundled, offline crop database with the planting guidance a gardener
actually needs when adding a plant: sun, spacing, sowing depth,
germination and maturity timing, plus a short how-to. Instant, private,
no API key, no network.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/crops", tags=["crops"])

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "crops.json"


@lru_cache(maxsize=1)
def _crops() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _summary(crop: dict) -> dict:
    return {
        "key": crop["key"],
        "name": crop["name"],
        "family": crop["family"],
        "sun": crop["sun"],
        "days_to_maturity": crop["days_to_maturity"],
    }


@router.get("")
def search_crops(q: str = "") -> dict:
    """Substring search over crop names + aliases. Empty query → []."""
    needle = (q or "").strip().lower()
    if not needle:
        return {"ok": True, "crops": []}
    matches = [
        c for c in _crops()
        if needle in c["name"].lower()
        or any(needle in a.lower() for a in c.get("aliases", []))
    ]
    # exact name matches first, then alphabetical
    matches.sort(key=lambda c: (0 if c["name"].lower().startswith(needle) else 1, c["name"]))
    return {"ok": True, "crops": [_summary(c) for c in matches[:20]]}


@router.get("/{key}")
def crop_detail(key: str) -> dict:
    """Full growing info for one crop."""
    for crop in _crops():
        if crop["key"] == key:
            return {"ok": True, "crop": crop}
    raise HTTPException(404, f"Unknown crop {key!r}.")
