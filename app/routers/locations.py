"""API router for garden locations (containers, beds)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Location

router = APIRouter(prefix="/api/locations", tags=["locations"])


def _get_or_404(session: Session, loc_id: int) -> Location:
    loc = session.get(Location, loc_id)
    if not loc:
        raise HTTPException(status_code=404, detail=f"Location {loc_id} not found")
    return loc


@router.get("/", response_model=List[Location])
def list_locations(
    type: Optional[str] = Query(None, description="Filter by type (Container, Raised Bed)"),
    session: Session = Depends(get_session)
) -> List[Location]:
    query = session.query(Location)
    if type:
        query = query.filter(Location.type == type)
    return query.all()


@router.post("/", response_model=Location, status_code=201)
def create_location(
    name: str,
    type: str = "Container",
    light: str = "Full Sun",
    pot_size: Optional[str] = None,
    notes: Optional[str] = None,
    session: Session = Depends(get_session)
) -> Location:
    loc = Location(
        name=name,
        type=type,
        light=light,
        pot_size=pot_size,
        notes=notes
    )
    existing = session.query(Location).filter(
        Location.location_id == loc.location_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Location with id '{loc.location_id}' already exists"
        )
    session.add(loc)
    session.commit()
    session.refresh(loc)
    return loc


@router.get("/{loc_id}", response_model=Location)
def get_location(loc_id: int, session: Session = Depends(get_session)) -> Location:
    return _get_or_404(session, loc_id)


@router.patch("/{loc_id}", response_model=Location)
def update_location(
    loc_id: int,
    payload: dict,
    session: Session = Depends(get_session)
) -> Location:
    loc = _get_or_404(session, loc_id)
    for key, value in payload.items():
        if hasattr(loc, key) and key != "id":
            setattr(loc, key, value)
    session.add(loc)
    session.commit()
    session.refresh(loc)
    return loc


@router.delete("/{loc_id}", status_code=204)
def delete_location(loc_id: int, session: Session = Depends(get_session)) -> None:
    loc = _get_or_404(session, loc_id)
    session.delete(loc)
    session.commit()