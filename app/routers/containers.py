"""API router for garden containers (backyard builder)."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Container

router = APIRouter(prefix="/api/containers", tags=["containers"])


def _get_or_404(session: Session, container_id: int) -> Container:
    container = session.get(Container, container_id)
    if not container:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found")
    return container


@router.get("/", response_model=List[Container])
def list_containers(
    year: Optional[int] = Query(None, description="Season year"),
    session: Session = Depends(get_session),
) -> List[Container]:
    query = session.query(Container).order_by(Container.name)
    if year is not None:
        query = query.filter(Container.season_year == year)
    return query.all()


@router.get("/years", response_model=List[int])
def list_years(session: Session = Depends(get_session)) -> List[int]:
    rows = session.query(Container.season_year).distinct().order_by(Container.season_year.desc()).all()
    return [r[0] for r in rows]


@router.post("/", response_model=Container, status_code=201)
def create_container(payload: dict, session: Session = Depends(get_session)) -> Container:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    container = Container(
        name=name,
        kind=(payload.get("kind") or "grow bag").strip(),
        size=(payload.get("size") or "").strip(),
        location_id=payload.get("location_id"),
        season_year=int(payload.get("season_year") or date.today().year),
        x=float(payload.get("x", 10)),
        y=float(payload.get("y", 10)),
        plant_id=payload.get("plant_id"),
        soil_notes=(payload.get("soil_notes") or "").strip(),
    )
    session.add(container)
    session.commit()
    session.refresh(container)
    return container


@router.get("/{container_id}", response_model=Container)
def get_container(container_id: int, session: Session = Depends(get_session)) -> Container:
    return _get_or_404(session, container_id)


@router.patch("/{container_id}", response_model=Container)
def update_container(
    container_id: int, payload: dict, session: Session = Depends(get_session)
) -> Container:
    container = _get_or_404(session, container_id)
    for key, value in payload.items():
        if hasattr(container, key) and key != "id":
            setattr(container, key, value)
    session.add(container)
    session.commit()
    session.refresh(container)
    return container


@router.delete("/{container_id}", status_code=204)
def delete_container(container_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get_or_404(session, container_id))
    session.commit()


@router.post("/copy-season", response_model=List[Container])
def copy_season(
    payload: dict, session: Session = Depends(get_session)
) -> List[Container]:
    """Copy one season's layout into another year (plant assignments included)."""
    try:
        from_year = int(payload["from_year"])
        to_year = int(payload["to_year"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="from_year and to_year are required")
    if from_year == to_year:
        raise HTTPException(status_code=422, detail="from_year and to_year must differ")
    existing = session.query(Container).filter(Container.season_year == to_year).count()
    if existing:
        raise HTTPException(status_code=409, detail=f"Season {to_year} already has containers")
    sources = session.query(Container).filter(Container.season_year == from_year).all()
    copies = []
    for src in sources:
        copy = Container(
            name=src.name, kind=src.kind, size=src.size,
            location_id=src.location_id, season_year=to_year,
            x=src.x, y=src.y, plant_id=src.plant_id, soil_notes=src.soil_notes,
        )
        session.add(copy)
        copies.append(copy)
    session.commit()
    for copy in copies:
        session.refresh(copy)
    return copies
