"""Fertilization log CRUD."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import FertilizationLog
from app.schemas import FertilizationCreate, FertilizationRead, FertilizationUpdate

router = APIRouter(prefix="/api/fertilizations", tags=["fertilizations"])


def _get_or_404(session: Session, log_id: int) -> FertilizationLog:
    log = session.get(FertilizationLog, log_id)
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fertilization log not found")
    return log


@router.get("", response_model=List[FertilizationRead])
def list_logs(
    session: Session = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[FertilizationLog]:
    stmt = (
        select(FertilizationLog)
        .order_by(FertilizationLog.date.desc(), FertilizationLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


@router.post("", response_model=FertilizationRead, status_code=status.HTTP_201_CREATED)
def create_log(
    payload: FertilizationCreate, session: Session = Depends(get_session)
) -> FertilizationLog:
    log = FertilizationLog(**payload.model_dump())
    log.fertilizer_name = log.fertilizer_name.strip()
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.get("/{log_id}", response_model=FertilizationRead)
def get_log(log_id: int, session: Session = Depends(get_session)) -> FertilizationLog:
    return _get_or_404(session, log_id)


@router.patch("/{log_id}", response_model=FertilizationRead)
def update_log(
    log_id: int, payload: FertilizationUpdate, session: Session = Depends(get_session)
) -> FertilizationLog:
    log = _get_or_404(session, log_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(log, key, value)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_log(log_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get_or_404(session, log_id))
    session.commit()
