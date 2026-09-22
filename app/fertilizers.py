"""API router for fertilizer catalog."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Fertilizer

router = APIRouter(prefix="/api/fertilizers", tags=["fertilizers"])


def _get_or_404(session: Session, fert_id: int) -> Fertilizer:
    fert = session.get(Fertilizer, fert_id)
    if not fert:
        raise HTTPException(status_code=404, detail=f"Fertilizer {fert_id} not found")
    return fert


@router.get("/", response_model=List[Fertilizer])
def list_fertilizers(session: Session = Depends(get_session)) -> List[Fertilizer]:
    return session.query(Fertilizer).all()


@router.post("/", response_model=Fertilizer, status_code=201)
def create_fertilizer(
    fert: Fertilizer,
    session: Session = Depends(get_session)
) -> Fertilizer:
    existing = session.query(Fertilizer).filter(
        Fertilizer.fertilizer_id == fert.fertilizer_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Fertilizer with id '{fert.fertilizer_id}' already exists"
        )
    session.add(fert)
    session.commit()
    session.refresh(fert)
    return fert


@router.get("/{fert_id}", response_model=Fertilizer)
def get_fertilizer(fert_id: int, session: Session = Depends(get_session)) -> Fertilizer:
    return _get_or_404(session, fert_id)


@router.patch("/{fert_id}", response_model=Fertilizer)
def update_fertilizer(
    fert_id: int,
    payload: dict,
    session: Session = Depends(get_session)
) -> Fertilizer:
    fert = _get_or_404(session, fert_id)
    for key, value in payload.items():
        if hasattr(fert, key) and key != "id":
            setattr(fert, key, value)
    session.add(fert)
    session.commit()
    session.refresh(fert)
    return fert


@router.delete("/{fert_id}", status_code=204)
def delete_fertilizer(fert_id: int, session: Session = Depends(get_session)) -> None:
    fert = _get_or_404(session, fert_id)
    session.delete(fert)
    session.commit()