"""Morning garden digest -> Discord webhook (optional).

Configure with env vars (see .env.example):
  DIGEST_ENABLED=true            # off by default — nothing is sent unless you opt in
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   # from Server Settings -> Integrations
  DIGEST_TIME=08:00              # 24h HH:MM, in DIGEST_TIMEZONE
  DIGEST_TIMEZONE=America/Chicago  # IANA zone for the send time; blank = server local

Or set it on the /settings page (the timezone field defaults to your
browser's timezone). Settings-page values always win over env vars.

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
from sqlmodel import Session, select

from app import ai_context as ai_context_mod
from app import frost as frost_mod
from app import llm as llm_mod
from app.database import get_session
from app.models import Setting
from app.routers.plants import ReminderRead, plant_reminders
from app.routers.stats import seed_calendar_rows
from app.schemas import SowRow

log = logging.getLogger("verdant.digest")

router = APIRouter(prefix="/api/digest", tags=["digest"])

# Discord hard-caps a message at 2000 chars; stay well under it so a long
# reminder list plus extras never silently fails to send.
DISCORD_SAFE_CHARS = 1900

AI_BRIEFING_SYSTEM = (
    "You are Verdant, a warm, knowledgeable gardening neighbor writing the "
    "opening lines of a morning garden briefing sent to Discord. Write 2-4 "
    "short sentences, plain text, no headers, no markdown tables. Name the "
    "top 1-2 priorities for the day and one encouraging line."
)


@dataclass
class DigestConfig:
    enabled: bool
    webhook_url: str
    time: str  # "HH:MM"
    timezone: str = ""  # IANA zone name; "" = server local time
    ai_briefing: bool = False  # optional LLM-written opener on the message


def resolve_digest_timezone(name: str):
    """Return a tzinfo for the digest send time.

    A configured IANA zone wins; anything blank or invalid falls back to the
    server's local timezone (and logs a warning for the invalid case).
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    fallback = datetime.now().astimezone().tzinfo
    name = (name or "").strip()
    if not name:
        return fallback
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        log.warning("Bad digest timezone %r; using server local time.", name)
        return fallback


def get_config() -> DigestConfig:
    enabled = os.getenv("DIGEST_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
    return DigestConfig(
        enabled=enabled,
        webhook_url=os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        time=os.getenv("DIGEST_TIME", "08:00").strip() or "08:00",
        timezone=os.getenv("DIGEST_TIMEZONE", "").strip(),
        ai_briefing=os.getenv("DIGEST_AI_BRIEFING", "").strip().lower() in ("1", "true", "yes", "on"),
    )


def effective_digest_config(session: Session) -> DigestConfig:
    """Digest config with /settings-page values winning over env vars.

    A key stored in the settings table always wins; keys never saved fall
    back to the env-var config, so existing .env setups keep working.
    """
    stored = {s.key: s.value for s in session.exec(select(Setting)).all()}
    env = get_config()

    def pick(key: str, env_val: str) -> str:
        return stored[key].strip() if key in stored else env_val

    if "digest_enabled" in stored:
        enabled = stored["digest_enabled"].strip().lower() in ("1", "true", "yes", "on")
    else:
        enabled = env.enabled
    if "digest_ai_briefing" in stored:
        ai_briefing = stored["digest_ai_briefing"].strip().lower() in ("1", "true", "yes", "on")
    else:
        ai_briefing = env.ai_briefing
    return DigestConfig(
        enabled=enabled,
        webhook_url=pick("discord_webhook_url", env.webhook_url),
        time=pick("digest_time", env.time) or "08:00",
        timezone=pick("digest_timezone", env.timezone),
        ai_briefing=ai_briefing,
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
    rain = f" · 🌧 {r.rain_note}" if r.rain_hold and r.rain_note else ""
    return f"{icon} **{r.plant_name}** — {action} · {when}{last}{rain}"


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


def ai_briefing_text(session: Session, message: str) -> Optional[str]:
    """Write a short LLM opening paragraph for the digest.

    Returns the briefing text, or None when AI is off / the provider fails.
    Never raises — the data-only message always survives.
    """
    try:
        if not llm_mod.get_config(session)["enabled"]:
            return None
        context = ai_context_mod.build_context(session)
        brief = llm_mod.chat(
            session,
            [
                {"role": "system", "content": AI_BRIEFING_SYSTEM},
                {
                    "role": "user",
                    "content": context
                    + "\n\nToday's garden data:\n"
                    + message
                    + "\n\nWrite the briefing paragraph.",
                },
            ],
            timeout=60,
        )
        brief = (brief or "").strip()
        return brief or None
    except Exception as exc:
        log.warning("AI briefing failed; sending data-only digest: %s", exc)
        return None


def _frost_alert_line(session: Session) -> Optional[str]:
    """One-line first-fall-frost alert when frost is near, or caution when it
    may have just hit. Returns None when there's nothing to warn about.

    Deliberately kept out of build_digest_message (that one is pure/tested
    without a session); the caller inserts this right after the header line.
    """
    try:
        frost, _src, _zone = frost_mod.resolve_frost(session, "first")
        if frost is None:
            return None
        days = (frost - date.today()).days
        if 0 <= days <= 14:
            return (
                f"❄️ First fall frost expected {frost.strftime('%a %b %d')} ({days} days) "
                "— bring tender plants in and harvest what's left."
            )
        if -7 <= days < 0:
            return (
                f"❄️ First fall frost may have hit {frost.strftime('%a %b %d')} "
                f"({abs(days)} days ago) — check tender plants and cover what's left."
            )
        return None
    except Exception as exc:
        log.warning("frost alert line failed: %s", exc)
        return None


def _message_with_extras(session: Session, message: str) -> str:
    """Attach the optional extras to the data message: the AI briefing opener
    (when the setting is on) and the frost alert line (when frost is near).
    Final order: briefing, header, frost alert, then the reminder sections."""
    cfg = effective_digest_config(session)
    if cfg.ai_briefing:
        brief = ai_briefing_text(session, message)
        if brief:
            candidate = "🌤️ " + brief.strip()[:600] + "\n\n" + message
            # Discord caps messages at 2000 chars; a too-long message fails
            # the whole send, so drop the briefing rather than the data.
            if len(candidate) <= DISCORD_SAFE_CHARS:
                message = candidate
    frost_line = _frost_alert_line(session)
    if frost_line:
        header, _, rest = message.partition("\n")
        message = header + "\n" + frost_line + ("\n" + rest if rest else "")
    return message


def run_digest(session: Session, webhook_url: str) -> str:
    """Build the digest from live reminder data and send it. Returns the message."""
    reminders = plant_reminders(session)
    sow_rows = seed_calendar_rows(session)
    message = build_digest_message(reminders, sow_rows=sow_rows)
    message = _message_with_extras(session, message)
    send_discord_message(webhook_url, message)
    log.info("Digest sent (%d chars).", len(message))
    return message


@router.get("/preview")
def preview_digest(session: Session = Depends(get_session)):
    """Show the message text that would be sent right now (does not send)."""
    message = build_digest_message(plant_reminders(session), sow_rows=seed_calendar_rows(session))
    return {"message": _message_with_extras(session, message)}


@router.post("/send")
def send_digest_now(session: Session = Depends(get_session)):
    """Build and send the digest immediately via the configured webhook."""
    cfg = effective_digest_config(session)
    if not cfg.enabled:
        raise HTTPException(status_code=400, detail="Digest is disabled (turn it on in Settings).")
    if not cfg.webhook_url:
        raise HTTPException(status_code=400, detail="No Discord webhook URL set (add one in Settings).")
    try:
        message = run_digest(session, cfg.webhook_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not send digest: {exc}")
    return {"sent": True, "message": message}
