"""Aggregate dashboard stats."""
from __future__ import annotations

from datetime import date as date_cls
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import FertilizationLog, ObservationImage, ObservationLog, Post, PostImage
from app.schemas import CalendarEntry, Stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=Stats, tags=["stats"])
def get_stats(session: Session = Depends(get_session)) -> Stats:
    def count(model) -> int:
        return session.exec(select(func.count()).select_from(model)).one()

    avg_health = session.exec(select(func.avg(ObservationLog.health_scale))).one()
    last_watered = session.exec(
        select(func.max(ObservationLog.date)).where(ObservationLog.watering_status.is_(True))
    ).one()

    return Stats(
        posts=count(Post),
        fertilizations=count(FertilizationLog),
        observations=count(ObservationLog),
        images=count(PostImage) + count(ObservationImage),
        avg_health=round(float(avg_health), 1) if avg_health is not None else None,
        last_watered=last_watered,
    )


@router.get("/calendar", response_model=List[CalendarEntry], tags=["calendar"])
def get_calendar(
    session: Session = Depends(get_session),
    plant: Optional[str] = Query(default=None, description="Filter by plant name"),
) -> List[CalendarEntry]:
    stmt = select(ObservationLog)
    if plant:
        stmt = stmt.where(func.lower(ObservationLog.plant_name).like(f"%{plant.lower()}%"))
    stmt = stmt.order_by(ObservationLog.date.desc(), ObservationLog.id.desc())
    observations = list(session.exec(stmt).all())
    entries = []
    for obs in observations:
        day = _coerce_date(obs.date)
        if day is None:
            continue  # skip rows with missing/malformed dates instead of 500ing
        entries.append(
            CalendarEntry(
                id=obs.id,
                date=day,
                plant_name=obs.plant_name,
                health_scale=obs.health_scale,
                watering_status=obs.watering_status,
                pest_sightings=obs.pest_sightings,
                notes=obs.notes,
            )
        )
    return entries


def _coerce_date(value) -> Optional[date_cls]:
    """Return a date for 'YYYY-MM-DD' strings, else None (never raise)."""
    if not value:
        return None
    try:
        return date_cls.fromisoformat(str(value)[:10])
    except ValueError:
        return None