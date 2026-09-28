"""Shared planting math: crop matching, sow-by dates, harvest forecasts.

Used by the Today view (harvest predictions) and the crop-lookup planting
calculator. Pure functions are unit-tested directly.
"""
from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
import json

from app import growstuff

# Days of safety margin between a crop's expected maturity and the first
# frost when computing the last safe sow date. Shown in the UI ("the math").
SOW_BUFFER_DAYS = 14

# "Cutting it close" threshold: sow-by dates within this many days get the
# amber warning instead of the green all-clear.
CLOSE_THRESHOLD_DAYS = 14

DATA_FILE = Path(__file__).resolve().parent / "data" / "crops.json"


@lru_cache(maxsize=1)
def _crops() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _norm(text: str | None) -> str:
    return (text or "").strip().lower()


def match_crop(plant_text: str) -> dict | None:
    """Match free text (variety + species) against the bundled crop guide.

    Returns {"crop": crop_dict, "variety": variety_dict | None,
    "days_to_maturity": int} for the best match, or None. Variety names win
    over crop names; longer (more specific) matches win ties.
    """
    needle = _norm(plant_text)
    if not needle:
        return None
    best = None
    best_score = -1
    for crop in _crops():
        for var in crop.get("varieties", []):
            vname = _norm(var.get("name"))
            if vname and vname in needle:
                score = 100 + len(vname)
                if score > best_score:
                    best_score = score
                    best = (crop, var)
        for alias in [crop.get("name", "")] + list(crop.get("aliases", [])):
            aname = _norm(alias)
            if aname and aname in needle:
                score = len(aname)
                if score > best_score:
                    best_score = score
                    best = (crop, None)
    if best is None:
        return None
    crop, var = best
    # Growstuff community medians (real gardens) win over the bundled
    # packet-claim numbers when cached data is available.
    community = growstuff.get(crop.get("key", ""))
    if community:
        maturity = int(community["median_days_to_first_harvest"])
        maturity_source = "community"
    else:
        maturity = (var.get("days_to_maturity") if var else None) or crop.get(
            "days_to_maturity"
        )
        maturity_source = "guide"
    if not maturity:
        return None
    return {
        "crop": crop,
        "variety": var,
        "days_to_maturity": int(maturity),
        "maturity_source": maturity_source,
        "crop_name": crop.get("name", ""),
        "variety_name": var.get("name") if var else None,
    }


def last_safe_sow_date(
    frost_date: date_cls, days_to_maturity: int, buffer_days: int = SOW_BUFFER_DAYS
) -> date_cls:
    """Last calendar date a crop can be sown and still mature before frost."""
    return frost_date - timedelta(days=int(days_to_maturity) + int(buffer_days))


def sow_verdict(sow_by: date_cls, today: date_cls | None = None) -> str:
    """'still_time' | 'close' | 'too_late' for a last-safe sow date."""
    today = today or date_cls.today()
    days_left = (sow_by - today).days
    if days_left < 0:
        return "too_late"
    if days_left < CLOSE_THRESHOLD_DAYS:
        return "close"
    return "still_time"


def harvest_forecast(
    plant_variety: str,
    plant_species: str,
    date_planted,
    plant_maturity: int | None,
    today: date_cls | None = None,
) -> dict | None:
    """Predicted harvest window for one plant. None when unknowable."""
    today = today or date_cls.today()
    if not date_planted:
        return None
    maturity = plant_maturity
    maturity_source = "plant"  # the plant's own recorded timing
    crop_name = None
    if not maturity:
        matched = match_crop(f"{plant_variety} {plant_species}")
        if not matched:
            return None
        maturity = matched["days_to_maturity"]
        maturity_source = matched["maturity_source"]
        crop_name = matched["crop_name"]
    ready = date_planted + timedelta(days=int(maturity))
    days_until = (ready - today).days
    return {
        "days_to_maturity": int(maturity),
        "maturity_source": maturity_source,
        "ready_date": ready.isoformat(),
        "days_until_ready": days_until,
        "status": "ready" if days_until <= 0 else "growing",
        "crop_name": crop_name,
    }
