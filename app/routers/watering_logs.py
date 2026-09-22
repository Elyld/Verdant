"""API router for watering history and method tracking."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import WateringLog, Location

router = APIRouter(prefix="/api/watering-logs", tags=["watering-logs"])


def _get_or_404(session: Session, watering_id: int) -> WateringLog:
    log = session.get(WateringLog, watering_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"Watering log {watering_id} not found")
    return log


@router.get("/", response_model=List[WateringLog])
def list_watering_logs(
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    method: Optional[str] = Query(None, description="Filter by watering method"),
    session: Session = Depends(get_session)
) -> List[WateringLog]:
    query = session.query(WateringLog)
    if location_id:
        query = query.filter(WateringLog.location_id == location_id)
    if date:
        query = query.filter(WateringLog.date == date)
    if method:
        query = query.filter(WateringLog.method == method)
    return query.all()


@router.post("/", response_model=WateringLog, status_code=201)
def create_watering_log(
    location_id: int,
    date: str,
    method: Optional[str] = None,
    amount: Optional[str] = None,
    notes: Optional[str] = None,
    session: Session = Depends(get_session)
) -> WateringLog:
    # Validate location exists
    session.get(Location, location_id)  # will raise if not found
    
    log = WateringLog(
        watering_id=f"WATER-{hash(f'{location_id}-{date}') % 1000:03d}",
        location_id=location_id,
        date=date,
        method=method,
        amount=amount,
        notes=notes
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.get("/{watering_id}", response_model=WateringLog)
def get_watering_log(watering_id: int, session: Session = Depends(get_session)) -> WateringLog:
    return _get_or_404(session, watering_id)


@router.patch("/{watering_id}", response_model=WateringLog)
def update_watering_log(
    watering_id: int,
    payload: dict,
    session: Session = Depends(get_session)
) -> WateringLog:
    log = _get_or_404(session, watering_id)
    for key, value in payload.items():
        if hasattr(log, key) and key != "id":
            setattr(log, key, value)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.delete("/{watering_id}", status_code=204)
def delete_watering_log(log_id: int, session: Session = Depends(get_session)) -> None:
    log = _get_or_404(session, log_id)
    session.delete(log)
    session.commit()