"""🏖️ Vacation caretaker sheet.

Bundles everything a garden-sitter needs into one dict so the printable
sheet (app/routers/caretaker.py) and the chat assistant can share it.

Never raises: every section is wrapped defensively and returns an empty
list/string on failure, so an empty or half-built garden still yields a
friendly page instead of an error.
"""
from __future__ import annotations

import logging
from datetime import date as Date
from datetime import timedelta
from typing import List, Optional

from sqlmodel import Session, select

from app.models import ObservationLog, PestLog, Plant

log = logging.getLogger("verdant.caretaker")

# Pest logs this old or newer are still worth a caretaker's attention.
PEST_WATCH_DAYS = 30


def _name(plant: Optional[Plant]) -> str:
    return (plant.variety_name if plant else None) or "?"


def watering_due(session: Session) -> List[dict]:
    """Plants due or overdue for water — reuses the reminder engine."""
    try:
        # Local import: plants router pulls in heavy dependencies.
        from app.routers.plants import plant_reminders

        rows = []
        for r in plant_reminders(session):
            if r.kind == "water" and r.status in ("overdue", "due", "soon"):
                rows.append({
                    "plant_id": r.plant_id,
                    "plant_name": r.plant_name,
                    "status": r.status,
                    "due_date": r.due_date.isoformat() if r.due_date else "",
                    "days_until_due": r.days_until_due,
                })
        return rows
    except Exception as exc:
        log.warning("caretaker watering_due failed: %s", exc)
        return []


def harvest_ready(session: Session) -> List[dict]:
    """Plants whose harvest forecast says 'ready' — same math as ai_context."""
    rows = []
    try:
        from app import planting as planting_mod

        plants = session.exec(
            select(Plant).where(Plant.status == "Growing")).all()
        for p in plants:
            planted = p.date_planted or p.date_started_indoors
            try:
                fc = planting_mod.harvest_forecast(
                    p.variety_name, p.species_type, planted,
                    p.days_to_maturity)
            except Exception:
                fc = None
            if fc and fc.get("status") == "ready":
                rows.append({
                    "plant_id": p.id,
                    "plant_name": p.variety_name or f"Plant #{p.id}",
                    "ready_date": fc.get("ready_date") or "",
                })
    except Exception as exc:
        log.warning("caretaker harvest_ready failed: %s", exc)
    return rows


def pest_watches(session: Session) -> List[dict]:
    """Unresolved pests, plus anything logged in the last month."""
    try:
        cutoff = (Date.today() - timedelta(days=PEST_WATCH_DAYS)).isoformat()
        entries = session.exec(
            select(PestLog)
            .where((PestLog.resolved == False) | (PestLog.date >= cutoff))  # noqa: E712
            .order_by(PestLog.date.desc(), PestLog.id.desc())).all()
        return [{
            "pest_name": e.pest_name or "Pest",
            "plant_name": _name(e.plant),
            "date": e.date or "",
            "treatment": e.treatment or "",
            "notes": e.notes or "",
            "resolved": bool(e.resolved),
        } for e in entries]
    except Exception as exc:
        log.warning("caretaker pest_watches failed: %s", exc)
        return []


def general_notes(session: Session) -> List[str]:
    """Useful-for-a-sitter notes: recent observation notes + plant notes."""
    notes: List[str] = []
    try:
        growing = session.exec(
            select(Plant).where(Plant.status == "Growing")).all()
        notes.append(f"{len(growing)} plants currently growing.")
        for p in growing:
            if p.notes:
                label = p.variety_name or f"Plant #{p.id}"
                notes.append(f"{label}: {p.notes.strip()}")
        # Recent observation notes (last 2 weeks) in case something was off.
        since = (Date.today() - timedelta(days=14)).isoformat()
        for o in session.exec(
                select(ObservationLog)
                .where(ObservationLog.date >= since)
                .order_by(ObservationLog.date.desc())).all():
            bit = (o.notes or "").strip()
            if bit:
                notes.append(f"{o.date} · {_name(o.plant)}: {bit}")
    except Exception as exc:
        log.warning("caretaker general_notes failed: %s", exc)
    return notes


def caretaker_data(session: Session) -> dict:
    """Everything a caretaker needs, as plain dicts/lists. Never raises."""
    return {
        "watering_due": watering_due(session),
        "harvest_ready": harvest_ready(session),
        "pest_watches": pest_watches(session),
        "general_notes": general_notes(session),
        "generated": Date.today().isoformat(),
    }
