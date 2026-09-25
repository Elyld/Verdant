"""API router for garden plants."""
from datetime import date as Date
from datetime import timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlmodel import or_

from app.database import get_session
from app.models import Plant, Location
from app.schemas import (
    ImageRead,
    PlantTimelineRead,
    ReminderRead,
    TimelineEvent,
    TimelapsePhoto,
)

router = APIRouter(prefix="/api/plants", tags=["plants"])


def _get_or_404(session: Session, plant_id: int) -> Plant:
    plant = session.get(Plant, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail=f"Plant {plant_id} not found")
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
    if plant.location_id:
        loc = session.get(Location, plant.location_id)
        if not loc:
            raise HTTPException(
                status_code=404,
                detail=f"Location {plant.location_id} not found"
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
    for key, value in payload.items():
        if hasattr(plant, key) and key != "id":
            setattr(plant, key, value)
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
            qty += f" ({harvest.weight} oz)"
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


@router.get("/reminders/list", response_model=List[ReminderRead])
def plant_reminders(session: Session = Depends(get_session)) -> List[ReminderRead]:
    """Watering/feeding reminders derived from each plant's care cadence."""
    from app.models import FertilizationLog, ObservationLog, WateringLog

    today = Date.today()
    reminders: list[ReminderRead] = []
    plants = session.query(Plant).filter(Plant.status == "Growing").all()

    for plant in plants:
        name = plant.variety_name or f"Plant #{plant.id}"

        # Last watered: latest watered observation OR latest watering log at its location.
        last_watered: Optional[Date] = None
        obs_dates = [
            _parse_day(o.date) for o in session.query(ObservationLog).filter(
                ObservationLog.plant_id == plant.id,
                ObservationLog.watering_status.is_(True),
            ).all()
        ]
        obs_dates = [d for d in obs_dates if d]
        if obs_dates:
            last_watered = max(obs_dates)
        water_clauses = [WateringLog.plant_id == plant.id]
        if plant.location_id:
            water_clauses.append(WateringLog.location_id == plant.location_id)
        log_dates = [
            _parse_day(w.date) for w in session.query(WateringLog).filter(
                or_(*water_clauses)
            ).all()
        ]
        log_dates = [d for d in log_dates if d]
        if log_dates and (last_watered is None or max(log_dates) > last_watered):
            last_watered = max(log_dates)

        # Last fed: latest fertilization for the plant.
        fed_dates = [
            _parse_day(f.date) for f in session.query(FertilizationLog).filter(
                FertilizationLog.plant_id == plant.id
            ).all()
        ]
        fed_dates = [d for d in fed_dates if d]
        last_fed = max(fed_dates) if fed_dates else None

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
    return reminders
