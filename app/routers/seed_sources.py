"""API router for seed sources."""
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import SeedSource, apply_patch

router = APIRouter(prefix="/api/seed-sources", tags=["seed-sources"])


def _get_or_404(session: Session, src_id: int) -> SeedSource:
    src = session.get(SeedSource, src_id)
    if not src:
        raise HTTPException(status_code=404, detail=f"Seed source {src_id} not found")
    return src


@router.get("/", response_model=List[SeedSource])
def list_seed_sources(
    source: Optional[str] = Query(None, description="Filter by vendor (Territorial Seed, etc.)"),
    session: Session = Depends(get_session)
) -> List[SeedSource]:
    query = session.query(SeedSource)
    if source:
        query = query.filter(SeedSource.source == source)
    return query.all()


def _coerce_dates(src: SeedSource) -> SeedSource:
    """SQLModel table models skip validation, so coerce ISO date strings by hand."""
    if isinstance(src.acquired_date, str):
        text = src.acquired_date.strip()
        try:
            src.acquired_date = date.fromisoformat(text)
        except ValueError:
            raise HTTPException(422, f"acquired_date {src.acquired_date!r} is not a valid YYYY-MM-DD date.")
    return src


@router.post("/", response_model=SeedSource, status_code=201)
def create_seed_source(
    src: SeedSource,
    session: Session = Depends(get_session)
) -> SeedSource:
    _coerce_dates(src)
    existing = session.query(SeedSource).filter(
        SeedSource.source_id == src.source_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Seed source with id '{src.source_id}' already exists"
        )
    session.add(src)
    session.commit()
    session.refresh(src)
    return src


@router.get("/{src_id}", response_model=SeedSource)
def get_seed_source(src_id: int, session: Session = Depends(get_session)) -> SeedSource:
    return _get_or_404(session, src_id)


@router.patch("/{src_id}", response_model=SeedSource)
def update_seed_source(
    src_id: int,
    payload: dict,
    session: Session = Depends(get_session)
) -> SeedSource:
    src = _get_or_404(session, src_id)
    # source_id is the stable public ID (CSV re-import keys on it): never rewritable.
    # acquired_date is a real Date column — apply_patch coerces it (422 on bad input).
    apply_patch(src, payload, exclude=("source_id",))
    session.add(src)
    session.commit()
    session.refresh(src)
    return src


@router.delete("/{src_id}", status_code=204)
def delete_seed_source(src_id: int, session: Session = Depends(get_session)) -> None:
    src = _get_or_404(session, src_id)
    session.delete(src)
    session.commit()