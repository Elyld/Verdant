"""Today view API — the morning-glance "what needs doing out there?\" page.

GET /api/today assembles: care due today (from the plant reminders logic),
harvest predictions (planted date + crop-guide maturity timing), and the
first-frost countdown. Weather + NOAA alerts are fetched by the page from
the existing /api/weather endpoints.
"""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import planting
from app import et as et_mod
from app.database import get_session
from app.models import Plant

router = APIRouter(prefix="/api/today", tags=["today"])


@router.get("")
def today_overview(session: Session = Depends(get_session)) -> dict:
    """Everything the Today page needs in one call."""
    from app import frost as frost_mod
    from app.routers.plants import plant_reminders

    today = Date.today()

    reminders = plant_reminders(session)
    due = [
        r.model_dump()
        for r in reminders
        if r.status in ("overdue", "due")
    ]

    forecast = []
    plants = session.query(Plant).filter(Plant.status == "Growing").all()
    for p in plants:
        planted = p.date_planted or p.date_started_indoors
        fc = planting.harvest_forecast(
            p.variety_name, p.species_type, planted, p.days_to_maturity, today=today
        )
        if not fc:
            continue
        forecast.append(
            {
                "plant_id": p.id,
                "plant_name": p.variety_name or f"Plant #{p.id}",
                "planted_date": planted.isoformat() if planted else None,
                **fc,
            }
        )
    # Ready now first, then soonest.
    forecast.sort(key=lambda f: (0 if f["status"] == "ready" else 1, f["ready_date"]))

    frost, source, zone = frost_mod.resolve_frost(session, "first", today=today)
    frost_info = None
    if frost is not None:
        frost_info = {
            "first_frost_date": frost.isoformat(),
            "days_until": (frost - today).days,
            "source": source,
            "label": frost_mod.frost_label(source, zone),
        }

    return {
        "ok": True,
        "date": today.isoformat(),
        "due": due,
        "harvest_forecast": forecast,
        "frost": frost_info,
        "watering_advice": et_mod.watering_advice(session),
    }
