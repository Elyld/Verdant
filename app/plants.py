"""API router for garden plants."""
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Plant, Location

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
    # Validate location exists
    if plant.location_id:
        loc = session.get(Location, plant.location_id)
        if not loc:
            raise HTTPException(
                status_code=404,
                detail=f"Location {plant.location_id} not found"
            )
    # Check for duplicate plant_id
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