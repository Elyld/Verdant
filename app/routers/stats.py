"""Aggregate dashboard stats."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import (
    FertilizationLog,
    ObservationImage,
    ObservationLog,
    Post,
    PostImage,
)
from app.schemas import Stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=Stats)
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
