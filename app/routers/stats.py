"""Aggregate dashboard stats."""
from __future__ import annotations

from datetime import date as date_cls
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import FertilizationLog, ObservationImage, ObservationLog, Post, PostImage
from app.schemas import CalendarEntry, ReviewRead, SowRow, Stats, TopPlant, YieldRow

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


@router.get("/review", response_model=ReviewRead, tags=["stats"])
def season_review(
    year: int = Query(default=None, description="Season year (defaults to current year)"),
    session: Session = Depends(get_session),
) -> ReviewRead:
    """Year-in-review aggregates: monthly activity, health trends, harvests."""
    from datetime import date as Date

    from app.models import Harvest, ObservationImage, WateringLog

    if year is None:
        year = Date.today().year
    prefix = f"{year}-"

    observations = list(
        session.exec(
            select(ObservationLog).where(ObservationLog.date.like(f"{prefix}%"))
        ).all()
    )
    by_month = [0] * 12
    health_sum = [0.0] * 12
    health_n = [0] * 12
    per_plant: dict[str, int] = {}
    per_day: dict[str, int] = {}
    pests = 0
    for obs in observations:
        try:
            month = int(str(obs.date)[5:7])
        except (ValueError, IndexError):
            continue
        if 1 <= month <= 12:
            by_month[month - 1] += 1
            health_sum[month - 1] += obs.health_scale
            health_n[month - 1] += 1
        per_plant[obs.plant_name] = per_plant.get(obs.plant_name, 0) + 1
        day = str(obs.date)[:10]
        per_day[day] = per_day.get(day, 0) + 1
        if (obs.pest_sightings or "").strip():
            pests += 1

    avg_health = [
        round(health_sum[i] / health_n[i], 1) if health_n[i] else None for i in range(12)
    ]
    top_plants = sorted(per_plant.items(), key=lambda kv: kv[1], reverse=True)[:5]
    busiest = max(per_day.items(), key=lambda kv: kv[1]) if per_day else (None, 0)

    harvests = list(
        session.exec(select(Harvest).where(Harvest.date.like(f"{prefix}%"))).all()
    )
    total_weight = sum(h.weight for h in harvests if h.weight) or None

    photos = session.exec(
        select(func.count())
        .select_from(ObservationImage)
        .where(ObservationImage.observation_id.in_(
            select(ObservationLog.id).where(ObservationLog.date.like(f"{prefix}%"))
        ))
    ).one() if observations else 0
    waterings = session.exec(
        select(func.count()).select_from(WateringLog).where(WateringLog.date.like(f"{prefix}%"))
    ).one()
    feedings = session.exec(
        select(func.count()).select_from(FertilizationLog).where(FertilizationLog.date.like(f"{prefix}%"))
    ).one()

    return ReviewRead(
        year=year,
        observations=len(observations),
        observations_by_month=by_month,
        avg_health_by_month=avg_health,
        harvest_count=len(harvests),
        harvest_weight=round(total_weight, 1) if total_weight else None,
        photos=int(photos),
        pests_noted=pests,
        waterings=int(waterings),
        feedings=int(feedings),
        top_plants=[TopPlant(plant_name=name, observations=count) for name, count in top_plants],
        busiest_day=Date.fromisoformat(busiest[0]) if busiest[0] else None,
        busiest_day_count=busiest[1],
    )


# --------------------------------------------------------------------------- #
# Yield leaderboard
# --------------------------------------------------------------------------- #
@router.get("/yield", response_model=List[YieldRow], tags=["stats"])
def yield_leaderboard(
    year: int = Query(default=None, description="Season year (defaults to current year)"),
    session: Session = Depends(get_session),
) -> List[YieldRow]:
    """Total harvested per plant, ranked — the variety smackdown."""
    from datetime import date as Date

    from app.models import Harvest, Plant

    if year is None:
        year = Date.today().year
    prefix = f"{year}-"
    harvests = session.exec(
        select(Harvest).where(Harvest.date.like(f"{prefix}%"))
    ).all()
    totals: dict[int, dict] = {}
    for h in harvests:
        entry = totals.setdefault(
            h.plant_id, {"qty": 0, "count": 0, "unit": h.unit or "fruit"}
        )
        entry["qty"] += h.quantity or 0
        entry["count"] += 1
    plants = {p.id: p for p in session.exec(select(Plant)).all()}
    rows = [
        YieldRow(
            plant_id=pid,
            variety_name=plants[pid].variety_name if pid in plants else f"Plant {pid}",
            total_quantity=entry["qty"],
            harvest_count=entry["count"],
            unit=entry["unit"],
        )
        for pid, entry in totals.items()
    ]
    rows.sort(key=lambda r: r.total_quantity, reverse=True)
    return rows


# --------------------------------------------------------------------------- #
# Seed-starting calendar
# --------------------------------------------------------------------------- #
def last_frost_date() -> date_cls:
    """Configurable via LAST_FROST_DATE (YYYY-MM-DD); defaults to Apr 15."""
    import os

    raw = os.getenv("LAST_FROST_DATE", "").strip()
    try:
        return date_cls.fromisoformat(raw)
    except ValueError:
        return date_cls(date_cls.today().year, 4, 15)


def _sow_weeks_before(species_type: str, category: str) -> int:
    s = f"{species_type or ''} {category or ''}".lower()
    if "pepper" in s:
        return 8
    if "tomato" in s:
        return 6
    return 6


def seed_calendar_rows(session: Session, today: date_cls = None) -> List[SowRow]:
    """Suggested indoor-start dates from last frost + per-crop offsets."""
    from datetime import timedelta

    from app import frost as frost_mod
    from app.models import Plant

    today = today or date_cls.today()
    resolved, source, _ = frost_mod.resolve_frost(session, "last", today=today)
    # Settings/zone values are annualized upcoming dates; the env var keeps
    # its long-standing raw behavior so existing setups don't shift.
    frost = resolved if source in ("exact", "zone") else last_frost_date()
    rows = []
    for p in session.exec(select(Plant)).all():
        if p.status not in ("Growing", "Planned", "Seedling"):
            continue
        if not p.days_to_maturity:
            continue
        suggested = frost - timedelta(weeks=_sow_weeks_before(p.species_type, p.category))
        started = _coerce_date(p.date_started_indoors)
        rows.append(
            SowRow(
                plant_id=p.id,
                variety_name=p.variety_name,
                category=p.category or "",
                suggested_start=suggested,
                days_until=(suggested - today).days,
                started_indoors=started,
            )
        )
    rows.sort(key=lambda r: r.suggested_start)
    return rows


@router.get("/seed-calendar", response_model=List[SowRow], tags=["stats"])
def seed_calendar(session: Session = Depends(get_session)) -> List[SowRow]:
    return seed_calendar_rows(session)


# --------------------------------------------------------------------------- #
# Frost countdown
# --------------------------------------------------------------------------- #
@router.get("/frost", tags=["stats"])
def frost_countdown(session: Session = Depends(get_session)) -> dict:
    """Days until the first anticipated frost (for the header countdown).

    Resolved from Settings exact date > USDA zone average > FIRST_FROST_DATE.
    Past dates roll to next year so the countdown never goes negative.
    """
    from app import frost as frost_mod

    frost, source, zone = frost_mod.resolve_frost(session, "first")
    if frost is None:
        return {"first_frost_date": None, "days_until": None, "source": None, "label": ""}
    return {
        "first_frost_date": frost.isoformat(),
        "days_until": (frost - date_cls.today()).days,
        "source": source,
        "label": frost_mod.frost_label(source, zone),
    }
