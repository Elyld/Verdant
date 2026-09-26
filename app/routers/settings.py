"""App settings API — backs the /settings page.

Stored in the `settings` key/value table. Digest keys saved here win over
the DIGEST_* env vars; frost keys feed the header countdown and the
seed-starting calendar (see app/frost.py for precedence).
"""
from __future__ import annotations

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

SETTING_KEYS = (
    "zone",
    "frost_date",
    "last_frost_date",
    "digest_enabled",
    "discord_webhook_url",
    "digest_time",
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


def _validate(payload: SettingsUpdate) -> None:
    if payload.zone and payload.zone not in frost_mod.VALID_ZONES:
        raise HTTPException(400, f"Unknown USDA zone {payload.zone!r} (want 3-10).")
    for label, raw in (
        ("frost_date", payload.frost_date),
        ("last_frost_date", payload.last_frost_date),
    ):
        if raw and frost_mod._parse_month_day(raw) is None:
            raise HTTPException(400, f"Bad {label} {raw!r} (want YYYY-MM-DD).")
    if not TIME_RE.match((payload.digest_time or "").strip()):
        raise HTTPException(400, f"Bad digest_time {payload.digest_time!r} (want HH:MM, 24h).")
    if payload.digest_enabled and not payload.discord_webhook_url.strip():
        raise HTTPException(400, "Digest is on but no Discord webhook URL was given.")


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
    return {
        "zone": frost_mod.get_setting(session, "zone"),
        "frost_date": frost_mod.get_setting(session, "frost_date"),
        "last_frost_date": frost_mod.get_setting(session, "last_frost_date"),
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
    session.commit()
    if _reschedule_digest is not None and payload.digest_time.strip() != old_time:
        _reschedule_digest()
    return current_settings(session)
