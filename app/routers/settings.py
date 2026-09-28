"""App settings API — backs the /settings page.

Stored in the `settings` key/value table. Digest keys saved here win over
the DIGEST_* env vars; frost keys feed the header countdown and the
seed-starting calendar (see app/frost.py for precedence); garden_lat /
garden_lon feed the weather strip and observation stamping, winning over
the GARDEN_LAT / GARDEN_LON env vars.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app import frost as frost_mod
from app.database import get_session
from app.routers.digest import effective_digest_config

router = APIRouter(prefix="/api/settings", tags=["settings"])

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Canonical mobile-tab keys. The frontend keeps the matching icon/label/href
# table (core.js NAV_SECTIONS); this set is the server-side source of truth
# for validation.
MOBILE_TAB_KEYS = frozenset({
    "home", "observations", "calendar", "photos", "plants", "seeds",
    "seedlings", "review", "import", "quick", "costs", "pests",
    "fertilizers", "planner", "tags",
})
DEFAULT_MOBILE_TABS = ["quick", "plants", "calendar", "planner"]
MAX_MOBILE_TABS = 4


def normalize_mobile_tabs(raw: str) -> str:
    """Validate + normalize the mobile_tabs setting.

    Stored as a JSON array string of tab keys, deduped, order preserved.
    Returns "" when unset. Raises 400 on a bad key or more than 4 tabs.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, f"Bad mobile_tabs {raw!r} (want a JSON array of tab keys).")
    if not isinstance(items, list):
        raise HTTPException(400, f"Bad mobile_tabs {raw!r} (want a JSON array of tab keys).")
    seen: list[str] = []
    for item in items:
        if item not in MOBILE_TAB_KEYS:
            raise HTTPException(400, f"Bad mobile_tabs key {item!r}.")
        if item not in seen:
            seen.append(item)
    if len(seen) > MAX_MOBILE_TABS:
        raise HTTPException(400, f"Bad mobile_tabs: at most {MAX_MOBILE_TABS} tabs.")
    return json.dumps(seen)

SETTING_KEYS = (
    "zone",
    "frost_date",
    "last_frost_date",
    "digest_enabled",
    "discord_webhook_url",
    "digest_time",
    "temperature_unit",
    "week_start",
    "default_weight_unit",
    "slideshow_interval",
    "confirm_water_all",
    "garden_lat",
    "garden_lon",
    "mobile_tabs",
    "local_ai_enabled",
    "local_ai_base_url",
    "local_ai_model",
)

# Set by app.main at startup so saving new digest settings re-arms the
# scheduler immediately instead of waiting for a container restart.
_reschedule_digest = None


def register_digest_rescheduler(fn) -> None:
    global _reschedule_digest
    _reschedule_digest = fn


class SettingsUpdate(BaseModel):
    zone: str = ""
    frost_date: str = ""  # exact first (fall) frost override, YYYY-MM-DD
    last_frost_date: str = ""  # exact last (spring) frost override, YYYY-MM-DD
    digest_enabled: bool = False
    discord_webhook_url: str = ""
    digest_time: str = "08:00"
    temperature_unit: str = "F"  # "F" or "C" — display unit for weather temps (stored Celsius)
    week_start: str = "0"  # "0" = Sunday, "1" = Monday — first column of the calendar
    default_weight_unit: str = "oz"  # prefill for the harvest form weight-unit select
    slideshow_interval: int = 5  # default slideshow autoplay interval, seconds
    confirm_water_all: bool = True  # confirm() before "Water all" on Quick Log
    garden_lat: str = ""  # garden latitude for the weather strip / stamping
    garden_lon: str = ""  # garden longitude — Settings win over GARDEN_LAT/LON env
    mobile_tabs: str = ""  # JSON array of mobile tab-bar keys (max 4); "" = defaults
    local_ai_enabled: bool = False  # "Tell Verdant what you did" card on Quick Log
    local_ai_base_url: str = "http://localhost:11434"  # Ollama-compatible server
    local_ai_model: str = "qwen3:4b"  # small model name, plain text


def _validate(payload: SettingsUpdate) -> None:
    if payload.zone and payload.zone not in frost_mod.VALID_ZONES:
        raise HTTPException(400, f"Unknown USDA zone {payload.zone!r} (want 3-10).")
    for label, raw in (
        ("frost_date", payload.frost_date),
        ("last_frost_date", payload.last_frost_date),
    ):
        if raw and frost_mod._parse_month_day(raw) is None:
            raise HTTPException(400, f"Bad {label} {raw!r} (want YYYY-MM-DD or MM-DD).")
    if not TIME_RE.match((payload.digest_time or "").strip()):
        raise HTTPException(400, f"Bad digest_time {payload.digest_time!r} (want HH:MM, 24h).")
    if payload.digest_enabled and not payload.discord_webhook_url.strip():
        raise HTTPException(400, "Digest is on but no Discord webhook URL was given.")
    if payload.temperature_unit not in ("F", "C"):
        raise HTTPException(400, f"Bad temperature_unit {payload.temperature_unit!r} (want 'F' or 'C').")
    if payload.week_start not in ("0", "1"):
        raise HTTPException(400, f"Bad week_start {payload.week_start!r} (want '0' for Sunday or '1' for Monday).")
    if payload.default_weight_unit not in ("oz", "g", "lb", "kg"):
        raise HTTPException(400, f"Bad default_weight_unit {payload.default_weight_unit!r} (want oz/g/lb/kg).")
    if payload.slideshow_interval not in (3, 5, 10, 30):
        raise HTTPException(400, f"Bad slideshow_interval {payload.slideshow_interval!r} (want 3/5/10/30).")
    for label, raw, lo, hi in (
        ("garden_lat", payload.garden_lat, -90, 90),
        ("garden_lon", payload.garden_lon, -180, 180),
    ):
        if raw.strip():
            try:
                value = float(raw)
            except ValueError:
                raise HTTPException(400, f"Bad {label} {raw!r} (want a number).")
            if not (lo <= value <= hi):
                raise HTTPException(400, f"Bad {label} {raw!r} (want {lo}..{hi}).")
    normalize_mobile_tabs(payload.mobile_tabs)  # 400 on bad key / >4 tabs
    base = (payload.local_ai_base_url or "").strip()
    if payload.local_ai_enabled:
        if not base or not base.startswith(("http://", "https://")):
            raise HTTPException(400, f"Bad local_ai_base_url {base!r} (want an http(s) URL).")
        if not (payload.local_ai_model or "").strip():
            raise HTTPException(400, "Local AI is on but no model name was given.")


def _frost_preview(session: Session, which: str) -> dict:
    frost_date, source, zone = frost_mod.resolve_frost(session, which)
    if frost_date is None:
        return {"date": None, "days_until": None, "label": "not set"}
    from datetime import date as date_cls

    return {
        "date": frost_date.isoformat(),
        "days_until": (frost_date - date_cls.today()).days,
        "label": frost_mod.frost_label(source, zone),
    }


def current_settings(session: Session) -> dict:
    """Everything the settings form needs, with the resolved frost preview."""
    digest = effective_digest_config(session)
    temp_unit = frost_mod.get_setting(session, "temperature_unit") or "F"
    if temp_unit not in ("F", "C"):
        temp_unit = "F"
    week_start = frost_mod.get_setting(session, "week_start") or "0"
    if week_start not in ("0", "1"):
        week_start = "0"
    default_weight_unit = frost_mod.get_setting(session, "default_weight_unit") or "oz"
    if default_weight_unit not in ("oz", "g", "lb", "kg"):
        default_weight_unit = "oz"
    try:
        slideshow_interval = int(frost_mod.get_setting(session, "slideshow_interval") or 5)
    except (TypeError, ValueError):
        slideshow_interval = 5
    if slideshow_interval not in (3, 5, 10, 30):
        slideshow_interval = 5
    confirm_water_all = (frost_mod.get_setting(session, "confirm_water_all") or "true") == "true"
    return {
        "zone": frost_mod.get_setting(session, "zone"),
        "frost_date": frost_mod.get_setting(session, "frost_date"),
        "last_frost_date": frost_mod.get_setting(session, "last_frost_date"),
        "garden_lat": frost_mod.get_setting(session, "garden_lat"),
        "garden_lon": frost_mod.get_setting(session, "garden_lon"),
        "mobile_tabs": frost_mod.get_setting(session, "mobile_tabs"),
        "temperature_unit": temp_unit,
        "week_start": week_start,
        "default_weight_unit": default_weight_unit,
        "slideshow_interval": slideshow_interval,
        "confirm_water_all": confirm_water_all,
        "local_ai_enabled": (frost_mod.get_setting(session, "local_ai_enabled") or "false") == "true",
        "local_ai_base_url": frost_mod.get_setting(session, "local_ai_base_url") or "http://localhost:11434",
        "local_ai_model": frost_mod.get_setting(session, "local_ai_model") or "qwen3:4b",
        "digest_enabled": digest.enabled,
        "discord_webhook_url": digest.webhook_url,
        "digest_time": digest.time,
        "frost_preview": {
            "first": _frost_preview(session, "first"),
            "last": _frost_preview(session, "last"),
        },
    }


@router.get("")
def get_settings(session: Session = Depends(get_session)) -> dict:
    return current_settings(session)


@router.put("")
def save_settings(payload: SettingsUpdate, session: Session = Depends(get_session)) -> dict:
    _validate(payload)
    old_time = frost_mod.get_setting(session, "digest_time")
    frost_mod.set_setting(session, "zone", payload.zone.strip())
    frost_mod.set_setting(session, "frost_date", payload.frost_date.strip())
    frost_mod.set_setting(session, "last_frost_date", payload.last_frost_date.strip())
    frost_mod.set_setting(session, "digest_enabled", "true" if payload.digest_enabled else "false")
    frost_mod.set_setting(session, "discord_webhook_url", payload.discord_webhook_url.strip())
    frost_mod.set_setting(session, "digest_time", payload.digest_time.strip() or "08:00")
    frost_mod.set_setting(session, "temperature_unit", payload.temperature_unit)
    frost_mod.set_setting(session, "week_start", payload.week_start)
    frost_mod.set_setting(session, "default_weight_unit", payload.default_weight_unit)
    frost_mod.set_setting(session, "slideshow_interval", str(payload.slideshow_interval))
    frost_mod.set_setting(session, "confirm_water_all", "true" if payload.confirm_water_all else "false")
    frost_mod.set_setting(session, "garden_lat", payload.garden_lat.strip())
    frost_mod.set_setting(session, "garden_lon", payload.garden_lon.strip())
    frost_mod.set_setting(session, "mobile_tabs", normalize_mobile_tabs(payload.mobile_tabs))
    frost_mod.set_setting(session, "local_ai_enabled", "true" if payload.local_ai_enabled else "false")
    frost_mod.set_setting(session, "local_ai_base_url", (payload.local_ai_base_url or "").strip() or "http://localhost:11434")
    frost_mod.set_setting(session, "local_ai_model", (payload.local_ai_model or "").strip() or "qwen3:4b")
    session.commit()
    if _reschedule_digest is not None and payload.digest_time.strip() != old_time:
        _reschedule_digest()
    return current_settings(session)
