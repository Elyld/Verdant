"""API router for watering logs."""
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import WateringLog, Location

router = APIRouter(prefix="/api/watering-logs", tags=["watering-logs"])


def _get_or_404(session: Session, log_id: int) -> WateringLog:
    log = session.get(WateringLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"Watering log {log_id} not found")
    return log


@router.get("/", response_model=List[WateringLog])
def list_watering_logs(
    location_id: Optional[int] = Query(None, description="Filter by location"),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    session: Session = Depends(get_session)
) -> List[WateringLog]:
    query = session.query(WateringLog)
    if location_id:
        query = query.filter(WateringLog.location_id == location_id)
    if start_date:
        query = query.filter(WateringLog.date >= start_date)
    if end_date:
        query = query.filter(WateringLog.date <= end_date)
    return query.all()


@router.post("/", response_model=WateringLog, status_code=201)
def create_watering_log(
    log: WateringLog,
    session: Session = Depends(get_session)
) -> WateringLog:
    # Validate location exists
    loc = session.get(Location, log.location_id)
    if not loc:
        raise HTTPException(
            status_code=404,
            detail=f"Location {log.location_id} not found"
        )
    # Check for duplicate watering_id
    existing = session.query(WateringLog).filter(
        WateringLog.watering_id == log.watering_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Watering log with id '{log.watering_id}' already exists"
        )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.get("/{log_id}", response_model=WateringLog)
def get_watering_log(log_id: int, session: Session = Depends(get_session)) -> WateringLog:
    return _get_or_404(session, log_id)


@router.patch("/{log_id}", response_model=WateringLog)
def update_watering_log(
    log_id: int,
    payload: dict,
    session: Session = Depends(get_session)
) -> WateringLog:
    log = _get_or_404(session, log_id)
    for key, value in payload.items():
        if hasattr(log, key) and key != "id":
            setattr(log, key, value)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.delete("/{log_id}", status_code=204)
def delete_watering_log(log_id: int, session: Session = Depends(get_session)) -> None:
    log = _get_or_404(session, log_id)
    session.delete(log)
    session.commit()