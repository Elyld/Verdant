"""API router for harvest tracking and yield data."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Harvest, Plant
from app.schemas import HarvestCreate
from app import units as units_mod

router = APIRouter(prefix="/api/harvests", tags=["harvests"])


def _get_or_404(session: Session, harvest_id: int) -> Harvest:
    harvest = session.get(Harvest, harvest_id)
    if not harvest:
        raise HTTPException(status_code=404, detail=f"Harvest {harvest_id} not found")
    return harvest


@router.get("/", response_model=List[Harvest])
def list_harvests(
    plant_id: Optional[int] = Query(None, description="Filter by plant ID"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    session: Session = Depends(get_session)
) -> List[Harvest]:
    query = session.query(Harvest)
    if plant_id:
        query = query.filter(Harvest.plant_id == plant_id)
    if date:
        query = query.filter(Harvest.date == date)
    return query.all()


@router.post("/", response_model=Harvest, status_code=201)
def create_harvest(
    payload: HarvestCreate,
    session: Session = Depends(get_session),
) -> Harvest:
    if not session.get(Plant, payload.plant_id):
        raise HTTPException(status_code=404, detail=f"Plant {payload.plant_id} not found")

    # Single source of truth for weighed harvests: if the unit itself is a
    # weight ("8 lbs"), the quantity IS the weight — derive it instead of
    # asking twice and risking the two disagreeing.
    weight = payload.weight
    weight_unit = units_mod.normalize_weight_unit(payload.weight_unit)
    if weight is None and units_mod.is_weight_unit(payload.unit):
        weight = float(payload.quantity)
        weight_unit = units_mod.normalize_weight_unit(payload.unit)

    harvest = Harvest(
        plant_id=payload.plant_id,
        date=payload.date.isoformat(),
        quantity=payload.quantity,
        unit=payload.unit,
        weight=weight,
        weight_unit=weight_unit,
        notes=payload.notes,
    )
    session.add(harvest)
    session.commit()
    session.refresh(harvest)
    return harvest


@router.get("/{harvest_id}", response_model=Harvest)
def get_harvest(harvest_id: int, session: Session = Depends(get_session)) -> Harvest:
    return _get_or_404(session, harvest_id)


@router.patch("/{harvest_id}", response_model=Harvest)
def update_harvest(
    harvest_id: int,
    payload: dict,
    session: Session = Depends(get_session)
) -> Harvest:
    harvest = _get_or_404(session, harvest_id)
    for key, value in payload.items():
        if hasattr(harvest, key) and key != "id":
            if key == "weight_unit":
                value = units_mod.normalize_weight_unit(value)
            setattr(harvest, key, value)
    session.add(harvest)
    session.commit()
    session.refresh(harvest)
    return harvest


@router.delete("/{harvest_id}", status_code=204)
def delete_harvest(harvest_id: int, session: Session = Depends(get_session)) -> None:
    harvest = _get_or_404(session, harvest_id)
    session.delete(harvest)
    session.commit()