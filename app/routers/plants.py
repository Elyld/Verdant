"""API router for garden plants."""
from datetime import date as Date
from datetime import timedelta
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.api_tokens import require_domain
from sqlalchemy.orm import Session
from sqlmodel import or_, select

from app.database import get_session
from app.models import Plant, Location, SeedPacket, apply_patch
from app.schemas import (
    ImageRead,
    PlantTimelineRead,
    ReminderRead,
    TimelineEvent,
    TimelapsePhoto,
)

router = APIRouter(prefix="/api/plants", tags=["plants"], dependencies=[Depends(require_domain("plants"))])


def _get_or_404(session: Session, plant_id: int) -> Plant:
    plant = session.get(Plant, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail=f"Plant {plant_id} not found")
    return plant


def _coerce_dates(plant: Plant) -> Plant:
    """SQLModel table models skip validation, so coerce ISO date strings by hand."""
    for field in ("date_started_indoors", "date_planted"):
        value = getattr(plant, field)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                setattr(plant, field, None)
                continue
            try:
                setattr(plant, field, Date.fromisoformat(text))
            except ValueError:
                raise HTTPException(422, f"{field} {value!r} is not a valid YYYY-MM-DD date.")
    return plant


@router.get("/", response_model=List[Plant])
def list_plants(
    location_id: Optional[int] = Query(None, description="Filter by location"),
    status: Optional[str] = Query(None, description="Filter by status (Growing, Harvested, Dead)"),
    species_type: Optional[str] = Query(None, description="Filter by type (Pepper, Tomato, etc.)"),
    session: Session = Depends(get_session)
) -> List[Plant]:
    query = session.query(Plant)
    if location_id:
        query = query.filter(Plant.location_id == location_id)
    if status:
        query = query.filter(Plant.status == status)
    if species_type:
        query = query.filter(Plant.species_type == species_type)
    return query.all()


@router.post("/", response_model=Plant, status_code=201)
def create_plant(
    plant: Plant,
    session: Session = Depends(get_session)
) -> Plant:
    _coerce_dates(plant)
    if plant.location_id:
        loc = session.get(Location, plant.location_id)
        if not loc:
            raise HTTPException(
                status_code=404,
                detail=f"Location {plant.location_id} not found"
            )
    if plant.seed_packet_id:
        if not session.get(SeedPacket, plant.seed_packet_id):
            raise HTTPException(
                status_code=404,
                detail=f"Seed packet {plant.seed_packet_id} not found"
            )
    existing = session.query(Plant).filter(
        Plant.plant_id == plant.plant_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Plant with id '{plant.plant_id}' already exists"
        )
    session.add(plant)
    session.commit()
    session.refresh(plant)
    return plant


# NOTE: "/covers" must be registered BEFORE "/{plant_id}", or FastAPI will
# try to parse "covers" as a plant id.


@router.get("/covers")
def plant_covers(session: Session = Depends(get_session)) -> Dict[int, str]:
    """Latest timeline photo per plant, in ONE query.

    The Plants page used to fetch /{id}/timeline once per card (thousands
    of requests at scale) just to find a cover photo; this bulk endpoint
    replaces that storm with a single call. Semantics match the old
    per-card logic: the photo that sorts last by (observation date,
    file path).
    """
    from app.models import ObservationImage, ObservationLog

    rows = session.exec(
        select(ObservationLog.plant_id, ObservationLog.date, ObservationImage.file_path)
        .join(ObservationImage, ObservationImage.observation_id == ObservationLog.id)
        .where(ObservationLog.plant_id.is_not(None))
        .where(ObservationLog.date != "")
        .order_by(ObservationLog.date.desc(), ObservationImage.file_path.desc())
    ).all()
    covers: Dict[int, str] = {}
    for plant_id, _day, path in rows:
        if plant_id not in covers:
            covers[plant_id] = path
    return covers


@router.get("/{plant_id}", response_model=Plant)
def get_plant(plant_id: int, session: Session = Depends(get_session)) -> Plant:
    return _get_or_404(session, plant_id)


@router.patch("/{plant_id}", response_model=Plant)
def update_plant(
    plant_id: int,
    payload: dict,
    session: Session = Depends(get_session)
) -> Plant:
    plant = _get_or_404(session, plant_id)
    # plant_id is the stable public ID (CSV re-import keys on it): never rewritable.
    if payload.get("seed_packet_id") is not None:
        if not session.get(SeedPacket, payload["seed_packet_id"]):
            raise HTTPException(
                status_code=404,
                detail=f"Seed packet {payload['seed_packet_id']} not found",
            )
    apply_patch(plant, payload, exclude=("plant_id",))
    session.add(plant)
    session.commit()
    session.refresh(plant)
    return plant


@router.delete("/{plant_id}", status_code=204)
def delete_plant(plant_id: int, session: Session = Depends(get_session)) -> None:
    plant = _get_or_404(session, plant_id)
    session.delete(plant)
    session.commit()

# --------------------------------------------------------------------------- #
# Timeline, reminders — the plant-profile backend
# --------------------------------------------------------------------------- #
def _parse_day(value) -> Optional[Date]:
    """Observation/fertilization dates are stored as strings; parse leniently."""
    if not value:
        return None
    try:
        return Date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@router.get("/{plant_id}/timeline", response_model=PlantTimelineRead)
def plant_timeline(plant_id: int, session: Session = Depends(get_session)) -> PlantTimelineRead:
    """Every event for one plant, newest first, plus chronological photos."""
    from app.models import FertilizationLog, Harvest, ObservationLog, WateringLog

    plant = _get_or_404(session, plant_id)
    events: list[TimelineEvent] = []

    observations = (
        session.query(ObservationLog)
        .filter(ObservationLog.plant_id == plant_id)
        .order_by(ObservationLog.date.desc(), ObservationLog.id.desc())
        .all()
    )
    photos: list[TimelapsePhoto] = []
    for obs in observations:
        day = _parse_day(obs.date)
        if day is None:
            continue
        images = [
            ImageRead(id=img.id, file_path=img.file_path, uploaded_at=img.uploaded_at)
            for img in (obs.images or [])
        ]
        events.append(TimelineEvent(
            kind="observation", date=day, id=obs.id,
            title=f"Observation — health {obs.health_scale}/10",
            detail=" ".join(part for part in [
                "Watered." if obs.watering_status else "",
                f"Pests: {obs.pest_sightings}" if obs.pest_sightings else "",
                obs.notes or "",
            ] if part).strip(),
            health_scale=obs.health_scale, images=images,
        ))
        for img in images:
            photos.append(TimelapsePhoto(
                file_path=img.file_path, date=day,
                caption=f"{plant.variety_name} — {day.isoformat()}",
            ))

    for fert in session.query(FertilizationLog).filter(
        FertilizationLog.plant_id == plant_id
    ).all():
        day = _parse_day(fert.date)
        if day is None:
            continue
        events.append(TimelineEvent(
            kind="fertilization", date=day, id=fert.id,
            title=f"Fed — {fert.fertilizer_name}",
            detail=" ".join(p for p in [fert.amount_used or "", fert.notes or ""] if p),
        ))

    for harvest in session.query(Harvest).filter(Harvest.plant_id == plant_id).all():
        day = _parse_day(harvest.date)
        if day is None:
            continue
        qty = f"{harvest.quantity} {harvest.unit}"
        if harvest.weight:
            wunit = (harvest.weight_unit or "oz").strip() or "oz"
            qty += f" ({harvest.weight:g} {wunit})"
        events.append(TimelineEvent(
            kind="harvest", date=day, id=harvest.id,
            title=f"Harvested {qty}",
            detail=harvest.notes or "",
        ))

    water_clauses = []
    if plant.location_id:
        water_clauses.append(WateringLog.location_id == plant.location_id)
    water_clauses.append(WateringLog.plant_id == plant_id)
    for log in session.query(WateringLog).filter(or_(*water_clauses)).all():
        day = _parse_day(log.date)
        if day is None:
            continue
        events.append(TimelineEvent(
            kind="watering", date=day, id=log.id,
            title=f"Watered ({log.method or 'unspecified method'})",
            detail=" ".join(p for p in [log.amount or "", log.notes or ""] if p),
        ))

    events.sort(key=lambda e: (e.date, e.id), reverse=True)
    photos.sort(key=lambda p: (p.date, p.file_path))
    name = plant.variety_name or f"Plant #{plant.id}"
    return PlantTimelineRead(plant_id=plant.id, plant_name=name, events=events, photos=photos)


def _reminder_status(days_until_due: Optional[int], cadence: Optional[int]) -> str:
    if not cadence:
        return "unset"
    if days_until_due is None:
        return "overdue"  # cadence set but never done → treat as overdue
    if days_until_due < 0:
        return "overdue"
    if days_until_due == 0:
        return "due"
    if days_until_due <= 2:
        return "soon"
    return "ok"


# Rain that makes watering pointless: ≥ 1/4" expected, or a ≥ 70% chance.
# Checked for today and tomorrow — tonight's storm covers today's chore.
RAIN_HOLD_INCHES = 0.25
RAIN_HOLD_PROB = 70


def rain_hold_note(session) -> Optional[str]:
    """'0.6" rain expected tomorrow' when the sky will water for you.

    Never raises: unconfigured weather or a dead forecast → None.
    """
    try:
        from app import weather as weather_mod

        fc = weather_mod.get_forecast(session)
        days = (fc or {}).get("daily") or []
        for i, label in ((0, "today"), (1, "tomorrow")):
            if i >= len(days):
                continue
            day = days[i] or {}
            precip_in = day.get("precip_in") or 0
            precip_prob = day.get("precip_prob") or 0
            if precip_in >= RAIN_HOLD_INCHES or precip_prob >= RAIN_HOLD_PROB:
                amt = (
                    f'{precip_in:g}" of rain'
                    if precip_in >= RAIN_HOLD_INCHES
                    else f"{precip_prob:g}% chance of rain"
                )
                return f"{amt} expected {label} — let the sky handle it"
    except Exception:
        pass
    return None


@router.get("/reminders/list", response_model=List[ReminderRead])
def plant_reminders(session: Session = Depends(get_session)) -> List[ReminderRead]:
    """Watering/feeding reminders derived from each plant's care cadence.

    Latest-care dates come from four bulk GROUP BY queries. The old code
    ran three queries PER plant (N+1); at a few thousand plants that took
    ~80s. Results are identical: max() over ISO YYYY-MM-DD strings orders
    chronologically, and malformed dates are excluded like before.
    """
    from app.models import FertilizationLog, ObservationLog, WateringLog
    from sqlmodel import func

    today = Date.today()
    reminders: list[ReminderRead] = []
    plants = session.query(Plant).filter(Plant.status == "Growing").all()
    plant_ids = [p.id for p in plants]
    loc_ids = list({p.location_id for p in plants if p.location_id})
    iso = "____-__-__"  # LIKE pattern: well-formed YYYY-MM-DD only

    def latest_per_id(model, id_col, date_col, ids, extra=()):
        if not ids:
            return {}
        return dict(session.exec(
            select(id_col, func.max(date_col))
            .where(id_col.in_(ids), date_col.like(iso), *extra)
            .group_by(id_col)
        ).all())

    obs_max = latest_per_id(ObservationLog, ObservationLog.plant_id,
                            ObservationLog.date, plant_ids,
                            (ObservationLog.watering_status.is_(True),))
    wplant_max = latest_per_id(WateringLog, WateringLog.plant_id,
                               WateringLog.date, plant_ids)
    wloc_max = latest_per_id(WateringLog, WateringLog.location_id,
                             WateringLog.date, loc_ids)
    fed_max = latest_per_id(FertilizationLog, FertilizationLog.plant_id,
                            FertilizationLog.date, plant_ids)

    def newest(*days: Optional[str]) -> Optional[Date]:
        parsed = [_parse_day(d) for d in days if d]
        parsed = [d for d in parsed if d]
        return max(parsed) if parsed else None

    for plant in plants:
        name = plant.variety_name or f"Plant #{plant.id}"

        # Last watered: latest watered observation OR latest watering log
        # for the plant itself or its location (same OR the old code used).
        last_watered = newest(
            obs_max.get(plant.id),
            wplant_max.get(plant.id),
            wloc_max.get(plant.location_id) if plant.location_id else None,
        )

        # Last fed: latest fertilization for the plant.
        last_fed = _parse_day(fed_max.get(plant.id))

        for kind, cadence, last in (
            ("water", plant.water_every_days, last_watered),
            ("feed", plant.feed_every_days, last_fed),
        ):
            due_date = (last + timedelta(days=cadence)) if (last and cadence) else None
            days_until = (due_date - today).days if due_date else None
            reminders.append(ReminderRead(
                plant_id=plant.id, plant_name=name, kind=kind,
                last_date=last, due_date=due_date,
                days_until_due=days_until,
                status=_reminder_status(days_until, cadence),
            ))

    # Most urgent first: overdue, due, soon, ok, unset.
    order = {"overdue": 0, "due": 1, "soon": 2, "ok": 3, "unset": 4}
    reminders.sort(key=lambda r: (order[r.status], r.days_until_due if r.days_until_due is not None else 999))
    # Weather-aware care: when rain's coming, watering reminders hold
    # instead of nagging. Advisory only — the reminder stays visible.
    rain_note = rain_hold_note(session)
    if rain_note:
        for r in reminders:
            if r.kind == "water" and r.status in ("overdue", "due", "soon"):
                r.rain_hold = True
                r.rain_note = rain_note
    return reminders
