"""Morning garden digest -> Discord webhook (optional).

Configure with env vars (see .env.example):
  DIGEST_ENABLED=true            # off by default — nothing is sent unless you opt in
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   # from Server Settings -> Integrations
  DIGEST_TIME=08:00              # 24h HH:MM, server local time

The message content comes from the plant-reminder engine (real data: what's
overdue / due today / coming up), formatted as a plain template. No LLM needed.

Endpoints:
  GET  /api/digest/preview  -> the message text that would be sent (no send)
  POST /api/digest/send     -> build + send now via the configured webhook
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.database import get_session
from app.routers.plants import ReminderRead, plant_reminders
from app.routers.stats import seed_calendar_rows
from app.schemas import SowRow

log = logging.getLogger("verdant.digest")

router = APIRouter(prefix="/api/digest", tags=["digest"])


@dataclass
class DigestConfig:
    enabled: bool
    webhook_url: str
    time: str  # "HH:MM"


def get_config() -> DigestConfig:
    enabled = os.getenv("DIGEST_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
    return DigestConfig(
        enabled=enabled,
        webhook_url=os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        time=os.getenv("DIGEST_TIME", "08:00").strip() or "08:00",
    )


KIND_ICON = {"water": "💧", "feed": "🧪"}


def _line(r: ReminderRead) -> str:
    icon = KIND_ICON.get(r.kind, "🌱")
    action = "water" if r.kind == "water" else "feed"
    if r.status == "overdue":
        when = f"{abs(r.days_until_due)}d overdue" if r.days_until_due is not None else "overdue"
    elif r.status == "due":
        when = "due today"
    else:  # soon
        when = f"due in {r.days_until_due}d ({r.due_date})" if r.days_until_due else f"due {r.due_date}"
    last = f" (last {r.last_date})" if r.last_date else ""
    return f"{icon} **{r.plant_name}** — {action} · {when}{last}"


def build_digest_message(
    reminders: List[ReminderRead],
    today: Optional[date] = None,
    sow_rows: Optional[List[SowRow]] = None,
) -> str:
    """Compose the Discord message from reminder data. Always returns text;
    when nothing needs attention it's a short all-clear."""
    today = today or date.today()
    header = f"🌱 **Morning garden check — {today.strftime('%a %b %d')}**"
    overdue = sorted(
        (r for r in reminders if r.status == "overdue"),
        key=lambda r: (r.days_until_due or 0),
    )
    due = [r for r in reminders if r.status == "due"]
    soon = sorted(
        (r for r in reminders if r.status == "soon"),
        key=lambda r: (r.days_until_due or 0),
    )
    sow_due = sorted(
        (
            r
            for r in (sow_rows or [])
            if r.started_indoors is None and 0 <= r.days_until <= 7
        ),
        key=lambda r: r.days_until,
    )
    if not overdue and not due and not soon and not sow_due:
        return f"{header}\n✅ All clear — nothing needs water or food today. Go enjoy the garden."
    parts = [header]
    if overdue:
        parts.append("\n🔴 **Overdue**")
        parts.extend(_line(r) for r in overdue)
    if due:
        parts.append("\n🟡 **Due today**")
        parts.extend(_line(r) for r in due)
    if soon:
        parts.append("\n🟢 **Coming up**")
        parts.extend(_line(r) for r in soon)
    if sow_due:
        parts.append("\n🌱 **Start indoors this week**")
        parts.extend(
            f"• {r.variety_name} — start by {r.suggested_start.strftime('%a %b %d')}"
            + (" (today!)" if r.days_until == 0 else f" (in {r.days_until}d)")
            for r in sow_due
        )
    return "\n".join(parts)


def send_discord_message(webhook_url: str, content: str, timeout: float = 15.0) -> None:
    """POST a plain-text message to a Discord webhook. Raises on failure."""
    if not webhook_url.startswith("https://"):
        raise ValueError("DISCORD_WEBHOOK_URL must be an https:// URL")
    resp = httpx.post(webhook_url, json={"content": content}, timeout=timeout)
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Discord webhook returned {resp.status_code}: {resp.text[:200]}")


def run_digest(session: Session, webhook_url: str) -> str:
    """Build the digest from live reminder data and send it. Returns the message."""
    reminders = plant_reminders(session)
    sow_rows = seed_calendar_rows(session)
    message = build_digest_message(reminders, sow_rows=sow_rows)
    send_discord_message(webhook_url, message)
    log.info("Digest sent (%d chars).", len(message))
    return message


@router.get("/preview")
def preview_digest(session: Session = Depends(get_session)):
    """Show the message text that would be sent right now (does not send)."""
    return {"message": build_digest_message(plant_reminders(session), sow_rows=seed_calendar_rows(session))}


@router.post("/send")
def send_digest_now(session: Session = Depends(get_session)):
    """Build and send the digest immediately via the configured webhook."""
    cfg = get_config()
    if not cfg.enabled:
        raise HTTPException(status_code=400, detail="Digest is disabled (set DIGEST_ENABLED=true).")
    if not cfg.webhook_url:
        raise HTTPException(status_code=400, detail="DISCORD_WEBHOOK_URL is not set.")
    try:
        message = run_digest(session, cfg.webhook_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not send digest: {exc}")
    return {"sent": True, "message": message}
