"""USDA-zone based frost date lookup and frost-date resolution.

USDA zones are coarse, so the dates below are approximate *average* frost
dates per zone — good enough for countdowns and sowing calendars, and a big
step up from an empty env var. Anyone who knows their exact local average
can set it directly (Settings page, or the FIRST_FROST_DATE / LAST_FROST_DATE
env vars), which always takes precedence over the zone lookup.

Precedence for each frost date:
    1. exact date in Settings (MM-DD / YYYY-MM-DD)
    2. zone-derived average from the Settings zone
    3. env var (FIRST_FROST_DATE / LAST_FROST_DATE)
    4. None (unknown)

Deliberate UI choices (exact date, zone) outrank env vars so a stale env
var can never silently shadow what the gardener picked in Settings.
"""
from __future__ import annotations

import os
from datetime import date as date_cls
from typing import Optional, Tuple

# Approximate average first FALL frost, by USDA zone: (month, day).
ZONE_FIRST_FROST: dict[str, Tuple[int, int]] = {
    "3": (9, 8),
    "4": (9, 21),
    "5": (10, 8),
    "6": (10, 21),
    "7": (10, 23),
    "8": (11, 8),
    "9": (11, 22),
    "10": (12, 8),
}

# Approximate average last SPRING frost, by USDA zone: (month, day).
ZONE_LAST_FROST: dict[str, Tuple[int, int]] = {
    "3": (5, 15),
    "4": (5, 10),
    "5": (4, 30),
    "6": (4, 15),
    "7": (4, 10),
    "8": (3, 20),
    "9": (2, 20),
    "10": (1, 30),
}

VALID_ZONES = sorted(ZONE_FIRST_FROST)


def get_setting(session, key: str) -> str:
    """Raw settings value ("" when unset). Session-typed loosely to avoid imports."""
    from app.models import Setting

    row = session.get(Setting, key)
    return row.value if row else ""


def set_setting(session, key: str, value: str) -> None:
    from app.models import Setting

    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value


def _parse_month_day(raw: str) -> Optional[Tuple[int, int]]:
    """Accept YYYY-MM-DD or MM-DD; return (month, day)."""
    raw = (raw or "").strip()
    for fmt_len in (10, 7):
        if len(raw) == fmt_len:
            try:
                parts = [int(p) for p in raw.split("-")]
                month, day = parts[-2], parts[-1]
                date_cls(2000, month, day)  # validates
                return month, day
            except (ValueError, IndexError):
                return None
    return None


def annualize(month: int, day: int, today: Optional[date_cls] = None) -> date_cls:
    """Next upcoming occurrence of an annual month/day (this year, else next)."""
    today = today or date_cls.today()
    this_year = date_cls(today.year, month, day)
    return this_year if this_year >= today else date_cls(today.year + 1, month, day)


def resolve_frost(
    session, which: str, today: Optional[date_cls] = None
) -> Tuple[Optional[date_cls], Optional[str], Optional[str]]:
    """Resolve an annual frost date.

    Returns (date, source, zone) where source is "exact", "env", or "zone".
    `which` is "first" (fall) or "last" (spring).
    """
    today = today or date_cls.today()
    exact_key, env_key, zone_map = (
        ("frost_date", "FIRST_FROST_DATE", ZONE_FIRST_FROST)
        if which == "first"
        else ("last_frost_date", "LAST_FROST_DATE", ZONE_LAST_FROST)
    )

    md = _parse_month_day(get_setting(session, exact_key))
    if md:
        return annualize(*md, today=today), "exact", None

    zone = get_setting(session, "zone").strip()
    if zone in zone_map:
        month, day = zone_map[zone]
        return annualize(month, day, today=today), "zone", zone

    md = _parse_month_day(os.getenv(env_key, ""))
    if md:
        return annualize(*md, today=today), "env", None

    return None, None, None


def frost_label(source: Optional[str], zone: Optional[str]) -> str:
    if source == "exact":
        return "your date"
    if source == "env":
        return "configured date"
    if source == "zone" and zone:
        return f"Zone {zone} average (approximate)"
    return ""
