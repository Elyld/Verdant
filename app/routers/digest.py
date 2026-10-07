"""Morning garden digest -> Discord webhook (optional).

Configure with env vars (see .env.example):
  DIGEST_ENABLED=true            # off by default — nothing is sent unless you opt in
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   # from Server Settings -> Integrations
  DIGEST_TIME=08:00              # 24h HH:MM, in DIGEST_TIMEZONE
  DIGEST_TIMEZONE=America/Chicago  # IANA zone for the send time; blank = server local

Or set it on the /settings page (the timezone field defaults to your
browser's timezone). Settings-page values always win over env vars.

The message content comes from the plant-reminder engine (real data: what's
overdue / due today / coming up), formatted as a plain template. Photos from
"this week last year" are attached as real image files (multipart upload),
not filenames. No LLM needed unless the optional AI briefing is on.

Reliability notes:
  - The message is capped under Discord's 2000-char limit by dropping the
    least-urgent sections first (AI briefing, then time-travel), so a long
    day never fails the whole send with a 400.
  - The webhook send retries once on transient failures (network / 429 / 5xx).
  - Every send attempt is logged, and the last successful send timestamp is
    stored (setting "digest_last_sent", shown on the Settings page).
  - On startup, if today's send time already passed with no successful send
    today, a catch-up digest goes out immediately instead of skipping the day.

Endpoints:
  GET  /api/digest/preview  -> the message text that would be sent (no send)
  POST /api/digest/send     -> build + send now via the configured webhook
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import ai_context as ai_context_mod
from app import frost as frost_mod
from app import llm as llm_mod
from app.database import UPLOAD_DIR, get_session
from app.models import Setting
from app.routers.plants import ReminderRead, plant_reminders
from app.routers.stats import seed_calendar_rows
from app.schemas import SowRow

log = logging.getLogger("verdant.digest")

router = APIRouter(prefix="/api/digest", tags=["digest"])

# Discord hard-caps a message at 2000 chars; stay well under it so a long
# reminder list plus extras never silently fails to send.
DISCORD_SAFE_CHARS = 1900
# Discord's free tier allows 8MB per attached file; stay a hair under it.
DISCORD_FILE_LIMIT = 7_500_000
# "This week last year" attaches at most this many photos.
DIGEST_MAX_PHOTOS = 4

AI_BRIEFING_SYSTEM = (
    "You are Verdant, a warm gardening neighbor writing the opening of a "
    "morning garden briefing sent to Discord. Write 1-2 SHORT sentences, "
    "plain text, no headers, no lists. Name only the single most important "
    "job today and one encouraging line. Keep it under 300 characters."
)


@dataclass
class DigestConfig:
    enabled: bool
    webhook_url: str
    time: str  # "HH:MM"
    timezone: str = ""  # IANA zone name; "" = server local time
    ai_briefing: bool = False  # optional LLM-written opener on the message


@dataclass
class DigestResult:
    """A fully built digest: message text plus photo attachments.

    photos: list of (filename, bytes, mime) ready for multipart upload.
    """

    message: str
    photos: list = field(default_factory=list)


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


def _truncate(text: str, max_chars: int) -> str:
    """Shorten text without ever cutting mid-word.

    Prefers ending at a sentence boundary; falls back to the last word
    boundary and appends an ellipsis.
    """
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for punct in (". ", "! ", "? "):
        idx = cut.rfind(punct)
        if idx >= max_chars // 3:
            return cut[: idx + 1].rstrip()
    idx = cut.rfind(" ")
    if idx > 0:
        return cut[:idx] + "…"
    return cut + "…"


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


# --------------------------------------------------------------------------- #
# User reminders: dedupe + plant grouping
# --------------------------------------------------------------------------- #

@dataclass
class _UserRem:
    title: str
    due_date: str
    notes: str = ""


def _normalize_title(title: str) -> str:
    """Lowercased title with parenthetical asides stripped — the dedupe key."""
    t = re.sub(r"\([^)]*\)", "", title or "")
    return " ".join(t.lower().split())


def _split_head(title: str) -> str:
    """The 'plant' part of a reminder title: parentheticals stripped, text
    before the first colon/dash separator. 'Fig (17-gal): move…' -> 'Fig'."""
    t = re.sub(r"\([^)]*\)", "", title or "").strip()
    for sep in (":", "—", "–", " - "):
        if sep in t:
            t = t.split(sep, 1)[0]
            break
    return " ".join(t.split())


def _dedupe_user_reminders(rems: list) -> List[_UserRem]:
    """Collapse reminders with the same normalized title AND same due date
    into one (notes merged). Kills the 'Plant carrots'/'plant carrots' dupes."""
    seen: dict[tuple[str, str], _UserRem] = {}
    order: list[tuple[str, str]] = []
    for r in rems:
        key = (_normalize_title(r.title), (r.due_date or "").strip())
        item = _UserRem(title=(r.title or "").strip(), due_date=(r.due_date or "").strip(),
                        notes=(r.notes or "").strip())
        if key in seen:
            prev = seen[key]
            merged = " / ".join(dict.fromkeys(x for x in [prev.notes, item.notes] if x))
            prev.notes = merged
        else:
            seen[key] = item
            order.append(key)
    return [seen[k] for k in order]


def _group_user_reminders(items: List[_UserRem]) -> List[List[_UserRem]]:
    """Group reminders that talk about the same plant: a single-word head
    ('Fig') pulls in longer heads that contain it ('move fig bucket…').
    Returns groups in first-appearance order; solo reminders stay solo."""
    heads = [_split_head(it.title) for it in items]
    lowers = [h.lower() for h in heads]
    singles: list[str] = []
    for h in lowers:
        if h and " " not in h and h not in singles:
            singles.append(h)
    groups: List[List[_UserRem]] = []
    used: set[int] = set()
    for word in singles:
        members = [
            i for i, h in enumerate(lowers)
            if i not in used and (h == word or (h != word and word in h.split()))
        ]
        if len(members) > 1:
            groups.append([items[i] for i in members])
            used.update(members)
    for i, it in enumerate(items):
        if i not in used:
            groups.append([it])
    return groups


def _reminder_when(due_date: str, today: date) -> str:
    try:
        due = date.fromisoformat(due_date) if due_date else None
    except ValueError:
        due = None
    if due is None:
        return "no date set"
    if due < today:
        n = (today - due).days
        return f"{n}d overdue" if n != 1 else "1d overdue"
    if due == today:
        return "due today"
    return f"due {due.strftime('%a %b %d')}"


def _reminder_action(title: str, head: str) -> str:
    """The action part of a grouped reminder: title minus its plant head."""
    t = re.sub(r"\([^)]*\)", "", title or "").strip()
    if head and t.lower().startswith(head.lower()):
        t = t[len(head):].lstrip(":—–- ").strip()
    return t or title.strip()


def _user_reminder_block(rems: list, today: date) -> Optional[str]:
    """One 🔔 block: deduped, plant-grouped reminder lines."""
    items = _dedupe_user_reminders(rems)
    if not items:
        return None
    lines = []
    for group in _group_user_reminders(items):
        if len(group) == 1:
            r = group[0]
            notes = f" — {_truncate(r.notes, 80)}" if r.notes else ""
            lines.append(f"• **{r.title}** · {_reminder_when(r.due_date, today)}{notes}")
        else:
            head = _split_head(group[0].title)
            lines.append(f"• **{head}**")
            for r in group:
                action = _reminder_action(r.title, head)
                notes = f" — {_truncate(r.notes, 80)}" if r.notes else ""
                lines.append(f"  · {action} · {_reminder_when(r.due_date, today)}{notes}")
    return "🔔 **Reminders**\n" + "\n".join(lines)


# --------------------------------------------------------------------------- #
# Message assembly with urgency-priority cap
# --------------------------------------------------------------------------- #

def _assemble(blocks: List[tuple]) -> str:
    """Join (priority, text) blocks in order; if over Discord's cap, drop the
    least-urgent blocks first (highest priority number). The header
    (priority 0) is never dropped."""
    blocks = list(blocks)
    while len(blocks) > 1:
        text = "\n".join(t for _, t in blocks)
        if len(text) <= DISCORD_SAFE_CHARS:
            break
        idx = max(range(len(blocks)), key=lambda i: (blocks[i][0], i))
        if blocks[idx][0] == 0:
            break
        del blocks[idx]
    return "\n".join(t for _, t in blocks)


def build_digest_message(
    reminders: List[ReminderRead],
    today: Optional[date] = None,
    sow_rows: Optional[List[SowRow]] = None,
    user_reminders: Optional[list] = None,
) -> str:
    """Compose the Discord message from reminder data. Always returns text;
    when nothing needs attention it's a short all-clear.

    Sections are urgency-ordered; if the message would exceed Discord's
    2000-char cap, the least-urgent sections are dropped instead of failing
    the send.
    """
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
    pending_rems = sorted(
        (r for r in (user_reminders or []) if not r.done and r.due_date),
        key=lambda r: (r.due_date >= today.isoformat(), r.due_date),
    )
    if not overdue and not due and not soon and not sow_due and not pending_rems:
        return f"{header}\n✅ All clear — nothing needs water or food today. Go enjoy the garden."
    blocks: List[tuple] = [(0, header)]
    if overdue:
        blocks.append((1, "🔴 **Overdue**\n" + "\n".join(_line(r) for r in overdue)))
    if due:
        blocks.append((2, "🟡 **Due today**\n" + "\n".join(_line(r) for r in due)))
    if soon:
        blocks.append((3, "🟢 **Coming up**\n" + "\n".join(_line(r) for r in soon)))
    if sow_due:
        blocks.append((
            4,
            "🌱 **Start indoors this week**\n" + "\n".join(
                f"• {r.variety_name} — start by {r.suggested_start.strftime('%a %b %d')}"
                + (" (today!)" if r.days_until == 0 else f" (in {r.days_until}d)")
                for r in sow_due
            ),
        ))
    rem_block = _user_reminder_block(pending_rems, today)
    if rem_block:
        blocks.append((5, rem_block))
    return _assemble(blocks)


# --------------------------------------------------------------------------- #
# "This week last year" photos as real attachments
# --------------------------------------------------------------------------- #

def _resolve_photo_path(file_path: str) -> Optional[Path]:
    """Map an AlbumImage file_path (/uploads/…) to a real file, with the same
    traversal guard the albums router uses. None when missing/unsafe."""
    prefix = "/uploads/"
    if not file_path.startswith(prefix):
        return None
    candidate = (UPLOAD_DIR / file_path[len(prefix):]).resolve()
    root = UPLOAD_DIR.resolve()
    if root != candidate and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def _mime_for(suffix: str) -> str:
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".webp": "image/webp", ".gif": "image/gif", ".heic": "image/heic",
    }.get(suffix.lower(), "image/jpeg")


def _read_photo_bytes(path: Path) -> Optional[tuple]:
    """Read photo bytes for a digest attachment: (bytes, mime) or None.

    Files over Discord's per-file limit are downscaled with PIL; if that
    fails or they're still too big, they're skipped (never fail the send).
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        log.info("digest photo unreadable %s: %s", path.name, exc)
        return None
    mime = _mime_for(path.suffix)
    if size <= DISCORD_FILE_LIMIT:
        try:
            return path.read_bytes(), mime
        except OSError as exc:
            log.info("digest photo unreadable %s: %s", path.name, exc)
            return None
    try:
        from PIL import Image

        with Image.open(path) as img:
            img.thumbnail((1600, 1600))
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=82)
            small = buf.getvalue()
        if len(small) <= DISCORD_FILE_LIMIT:
            log.info("digest photo downscaled %s (%d → %d bytes)", path.name, size, len(small))
            return small, "image/jpeg"
    except Exception as exc:
        log.warning("digest photo downscale failed %s: %s", path.name, exc)
    log.info("digest photo skipped (too large): %s (%d bytes)", path.name, size)
    return None


def collect_time_travel_photos(
    session: Session, today: Optional[date] = None, max_photos: int = DIGEST_MAX_PHOTOS
) -> list:
    """Real image files for 'this week last year': [(filename, bytes, mime)].

    Missing or unreadable files are skipped with a log line — a gap in the
    photo history never breaks the digest.
    """
    from app import time_travel as time_travel_mod

    try:
        data = time_travel_mod.this_week_last_year(session, today=today or date.today())
    except Exception as exc:
        log.warning("time-travel photo lookup failed: %s", exc)
        return []
    out = []
    for p in data.get("photos", [])[:max_photos]:
        path = _resolve_photo_path(p.get("file_path") or "")
        if path is None:
            log.info("digest photo skipped (file missing): %s", p.get("file_path"))
            continue
        blob = _read_photo_bytes(path)
        if blob is None:
            continue
        data_bytes, mime = blob
        out.append((path.name, data_bytes, mime))
    return out


def _time_travel_block(session: Session, today: date, photo_count: int) -> Optional[str]:
    """🕰️ text block: journal notes/harvests as text, photos referenced as
    attachments (never bare filenames). Returns None when there's nothing."""
    from app import time_travel as time_travel_mod

    try:
        data = time_travel_mod.this_week_last_year(session, today=today)
    except Exception as exc:
        log.warning("time-travel section failed: %s", exc)
        return None
    lines = []
    if photo_count:
        noun = "photo" if photo_count == 1 else "photos"
        lines.append(f"• 📷 {photo_count} {noun} from this week last year attached below 👇")
    for entry in data.get("logs", [])[:6]:
        label = "🧺" if entry.get("kind") == "harvest" else "📝"
        text = f"{entry.get('date')} — {entry.get('plant_name')}"
        if entry.get("notes"):
            text += f": {_truncate(entry['notes'], 60)}"
        lines.append(f"• {label} {text}")
    if not lines:
        return None
    return "🕰️ **This week last year**\n" + "\n".join(lines)


# --------------------------------------------------------------------------- #
# Webhook send (multipart when photos are attached) with one retry
# --------------------------------------------------------------------------- #

def send_discord_digest(
    webhook_url: str,
    content: str,
    photos: Optional[list] = None,
    timeout: float = 15.0,
    retry_delay: float = 5.0,
) -> None:
    """POST the digest to a Discord webhook, attaching photos as real files.

    photos: [(filename, bytes, mime)]. Retries once after retry_delay on
    transient failures (network errors, 429, 5xx). Raises on failure.
    """
    if not webhook_url.startswith("https://"):
        raise ValueError("DISCORD_WEBHOOK_URL must be an https:// URL")
    photos = list(photos or [])

    def _post():
        if photos:
            files = [
                (f"files[{i}]", (name, blob, mime))
                for i, (name, blob, mime) in enumerate(photos)
            ]
            return httpx.post(
                webhook_url,
                data={"payload_json": json.dumps({"content": content})},
                files=files,
                timeout=timeout,
            )
        return httpx.post(webhook_url, json={"content": content}, timeout=timeout)

    def _retryable(resp) -> bool:
        return resp.status_code == 429 or resp.status_code >= 500

    try:
        resp = _post()
    except httpx.TransportError as exc:
        log.warning("Digest webhook transport error (%s); retrying once.", exc)
        time.sleep(retry_delay)
        resp = _post()
    if resp.status_code in (200, 204):
        log.info("Digest webhook accepted (%d).", resp.status_code)
        return
    if _retryable(resp):
        log.warning("Digest webhook returned %d; retrying once after %.0fs.",
                    resp.status_code, retry_delay)
        time.sleep(retry_delay)
        resp = _post()
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Discord webhook returned {resp.status_code}: {resp.text[:200]}")
    log.info("Digest webhook accepted on retry (%d).", resp.status_code)


def send_discord_message(webhook_url: str, content: str, timeout: float = 15.0) -> None:
    """POST a plain-text message to a Discord webhook. Raises on failure."""
    send_discord_digest(webhook_url, content, timeout=timeout)


# --------------------------------------------------------------------------- #
# Optional extras: AI briefing, frost alert, frost gamble, time travel
# --------------------------------------------------------------------------- #

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
        brief = _truncate(brief or "", 300)
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


def _safe_gamble_block(session: Session) -> Optional[str]:
    try:
        from app import frost_gamble as frost_gamble_mod

        return frost_gamble_mod.digest_block(session) or None
    except Exception as exc:
        log.warning("frost gamble block failed: %s", exc)
        return None


def _enforce_cap(message: str, has_briefing: bool, has_tt: bool) -> str:
    """Last-resort cap: if the extras pushed the message over Discord's
    limit, drop the AI briefing first, then the time-travel section, then
    hard-truncate at a word boundary. The data sections always survive."""
    if len(message) <= DISCORD_SAFE_CHARS:
        return message
    if has_briefing:
        head, _, rest = message.partition("\n\n")
        if head.startswith("🌤️"):
            message = rest
            log.info("Digest over cap: dropped AI briefing.")
    if len(message) <= DISCORD_SAFE_CHARS:
        return message
    if has_tt:
        idx = message.find("\n\n🕰️ **This week last year**")
        if idx != -1:
            message = message[:idx]
            log.info("Digest over cap: dropped time-travel section.")
    if len(message) <= DISCORD_SAFE_CHARS:
        return message
    log.warning("Digest still over cap after dropping extras; hard-truncating.")
    return _truncate(message, DISCORD_SAFE_CHARS)


def _message_with_extras(
    session: Session, message: str, today: date, photo_count: int = 0
) -> tuple:
    """Attach the optional extras to the data message: the AI briefing opener
    (when the setting is on), the frost alert line (when frost is near), the
    frost-gamble block, and the time-travel section.

    Final order: briefing, header, frost alert, gamble, reminder sections,
    time travel. Returns (message, time_travel_included).
    """
    cfg = effective_digest_config(session)
    briefing = ai_briefing_text(session, message) if cfg.ai_briefing else None
    frost_line = _frost_alert_line(session)
    gamble = _safe_gamble_block(session)
    tt = _time_travel_block(session, today, photo_count)

    header, _, rest = message.partition("\n")
    extra_lines = [x for x in (frost_line, gamble) if x]
    body = header + ("\n" + "\n".join(extra_lines) if extra_lines else "")
    if rest:
        body += "\n" + rest
    full = (f"🌤️ {briefing}\n\n" if briefing else "") + body
    if tt:
        full += "\n\n" + tt
    full = _enforce_cap(full, has_briefing=bool(briefing), has_tt=bool(tt))
    tt_included = bool(tt) and "🕰️ **This week last year**" in full
    return full, tt_included


def _pending_user_reminders(session: Session) -> list:
    """Dated reminders the gardener confirmed via chat. Never raises."""
    from app.models import UserReminder

    try:
        return session.exec(
            select(UserReminder)
            .where(UserReminder.done == False)  # noqa: E712
            .order_by(UserReminder.due_date, UserReminder.id)).all()
    except Exception as exc:
        log.warning("user reminders fetch failed: %s", exc)
        return []


def _record_send(session: Session, ok: bool, error: str = "") -> None:
    """Store the last digest send outcome (shown on the Settings page)."""
    try:
        if ok:
            frost_mod.set_setting(session, "digest_last_sent", datetime.now(timezone.utc).isoformat())
            frost_mod.set_setting(session, "digest_last_error", "")
        else:
            frost_mod.set_setting(
                session, "digest_last_error",
                f"{datetime.now(timezone.utc).isoformat()} — {error[:200]}",
            )
        session.commit()
    except Exception:
        log.warning("could not record digest send status", exc_info=True)
        try:
            session.rollback()
        except Exception:
            pass


def build_full_digest(session: Session, today: Optional[date] = None) -> DigestResult:
    """Build the complete digest: message text plus photo attachments.

    A failure in any one section degrades to a partial digest (or a short
    fallback message) instead of sending nothing at all.
    """
    today = today or date.today()
    try:
        reminders = plant_reminders(session)
        sow_rows = seed_calendar_rows(session)
        message = build_digest_message(
            reminders, today=today, sow_rows=sow_rows,
            user_reminders=_pending_user_reminders(session),
        )
    except Exception as exc:
        log.exception("digest build failed; sending fallback message")
        message = (
            f"🌱 **Morning garden check — {today.strftime('%a %b %d')}**\n"
            f"⚠️ The full digest couldn't be built today ({exc}). "
            "Open Verdant for the details."
        )
        return DigestResult(message=message)
    try:
        photos = collect_time_travel_photos(session, today)
    except Exception as exc:
        log.warning("digest photo collection failed: %s", exc)
        photos = []
    message, tt_included = _message_with_extras(session, message, today, photo_count=len(photos))
    if not tt_included:
        photos = []  # no context for them — don't send stray attachments
    return DigestResult(message=message, photos=photos)


def run_digest(session: Session, webhook_url: str) -> str:
    """Build the digest from live reminder data and send it. Returns the message."""
    result = build_full_digest(session)
    try:
        send_discord_digest(webhook_url, result.message, result.photos)
    except Exception as exc:
        _record_send(session, ok=False, error=str(exc))
        raise
    _record_send(session, ok=True)
    log.info("Digest sent (%d chars, %d photos).", len(result.message), len(result.photos))
    return result.message


@router.get("/preview")
def preview_digest(session: Session = Depends(get_session)):
    """Show the message text that would be sent right now (does not send)."""
    result = build_full_digest(session)
    return {"message": result.message, "photos": len(result.photos)}


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
