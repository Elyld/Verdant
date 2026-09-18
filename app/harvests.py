"""API router for harvest logs."""
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Harvest, Plant

router = APIRouter(prefix="/api/harvests", tags=["harvests"])


def _get_or_404(session: Session, harvest_id: int) -> Harvest:
    harvest = session.get(Harvest, harvest_id)
    if not harvest:
        raise HTTPException(status_code=404, detail=f"Harvest {harvest_id} not found")
    return harvest


@router.get("/", response_model=List[Harvest])
def list_harvests(
    plant_id: Optional[int] = Query(None, description="Filter by plant"),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    session: Session = Depends(get_session)
) -> List[Harvest]:
    query = session.query(Harvest)
    if plant_id:
        query = query.filter(Harvest.plant_id == plant_id)
    if start_date:
        query = query.filter(Harvest.date >= start_date)
    if end_date:
        query = query.filter(Harvest.date <= end_date)
    return query.all()


@router.post("/", response_model=Harvest, status_code=201)
def create_harvest(
    harvest: Harvest,
    session: Session = Depends(get_session)
) -> Harvest:
    # Validate plant exists
    plant = session.get(Plant, harvest.plant_id)
    if not plant:
        raise HTTPException(
            status_code=404,
            detail=f"Plant {harvest.plant_id} not found"
        )
    # Check for duplicate harvest_id
    existing = session.query(Harvest).filter(
        Harvest.harvest_id == harvest.harvest_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Harvest with id '{harvest.harvest_id}' already exists"
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