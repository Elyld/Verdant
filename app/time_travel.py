"""🕰️ This week last year — a little time-travel for the garden journal.

Finds journal entries from the same ISO calendar week one year ago:
ObservationLogs, Harvests, and AlbumImages (photo metadata). Pure data
function plus a compact digest line. Never raises.
"""
from __future__ import annotations

import logging
from datetime import date as Date
from datetime import timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import AlbumImage, Harvest, ObservationLog

log = logging.getLogger("verdant.time_travel")

MAX_ITEMS = 10
MAX_DIGEST_LINES = 6


def _week_window(today: Date) -> tuple[str, str]:
    """7-day window of the same ISO week one year ago, as ISO strings."""
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(weeks=52)
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _photo_date(img: AlbumImage) -> str:
    ts = img.taken_at or img.imported_at
    if ts is None:
        return ""
    try:
        return ts.date().isoformat()
    except Exception:
        return ""


def this_week_last_year(session: Session, today: Optional[Date] = None) -> dict:
    """Journal entries from the same ISO week one year ago.

    Returns {"photos": [{file_path, date, plant_name}],
              "logs":   [{date, plant_name, notes, kind}]}.
    Capped at ~10 items total, newest first. Never raises.
    """
    today = today or Date.today()
    start, end = _week_window(today)
    photos: list[dict] = []
    logs: list[dict] = []
    try:
        for o in session.exec(
                select(ObservationLog)
                .where(ObservationLog.date >= start, ObservationLog.date <= end)
                .order_by(ObservationLog.date.desc())).all():
            notes = (o.notes or "").strip()[:140]
            logs.append({
                "date": o.date or "",
                "plant_name": (o.plant.variety_name if o.plant else o.plant_name)
                or "?",
                "notes": notes,
                "kind": "note",
            })

        for h in session.exec(
                select(Harvest)
                .where(Harvest.date >= start, Harvest.date <= end)
                .order_by(Harvest.date.desc())).all():
            name = (h.plant.variety_name if h.plant else None) or "?"
            qty = h.quantity or 0
            logs.append({
                "date": h.date or "",
                "plant_name": name,
                "notes": f"harvested {qty} {h.unit or 'fruit'}".strip(),
                "kind": "harvest",
            })

        for img in session.exec(select(AlbumImage)).all():
            d = _photo_date(img)
            if d and start <= d <= end:
                photos.append({
                    "file_path": img.file_path,
                    "date": d,
                    "plant_name": (img.plant.variety_name if img.plant else None)
                    or (img.title or "garden photo"),
                })

        photos.sort(key=lambda p: p["date"], reverse=True)
        logs.sort(key=lambda l: (l["date"], l["kind"]), reverse=True)

        # Interleave-ish: keep photos first (visual hook), cap total at 10.
        photos = photos[:MAX_ITEMS]
        logs = logs[:MAX_ITEMS]
        total = len(photos) + len(logs)
        if total > MAX_ITEMS:
            overflow = total - MAX_ITEMS
            logs = logs[:max(0, len(logs) - overflow)]
        return {"photos": photos, "logs": logs}
    except Exception as exc:
        log.warning("this_week_last_year failed: %s", exc)
        return {"photos": [], "logs": []}


def digest_section(session: Session, today: Optional[Date] = None) -> Optional[str]:
    """Compact '🕰️ This week last year' block for the Discord digest.

    Returns None when there's nothing to show (the integrator skips it).
    """
    try:
        data = this_week_last_year(session, today=today)
        lines: list[str] = []
        for p in data["photos"]:
            lines.append(f"📷 {p['date']} — {p['plant_name']}")
            if len(lines) >= MAX_DIGEST_LINES:
                break
        for entry in data["logs"]:
            if len(lines) >= MAX_DIGEST_LINES:
                break
            label = "🧺" if entry["kind"] == "harvest" else "📝"
            text = f"{entry['date']} — {entry['plant_name']}"
            if entry["notes"]:
                text += f": {entry['notes'][:60]}"
            lines.append(f"{label} {text}")
        if not lines:
            return None
        return "🕰️ **This week last year**\n" + "\n".join("• " + ln for ln in lines)
    except Exception as exc:
        log.warning("digest_section failed: %s", exc)
        return None
