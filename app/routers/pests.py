"""API router for the pest & treatment log."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import PestLog, Plant
from app.schemas import PestLogCreate, PestLogRead

router = APIRouter(prefix="/api/pests", tags=["pests"])


def _get_or_404(session: Session, pest_id: int) -> PestLog:
    log = session.get(PestLog, pest_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"Pest log {pest_id} not found")
    return log


@router.get("/", response_model=List[PestLogRead])
def list_pest_logs(
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    session: Session = Depends(get_session),
) -> List[PestLog]:
    query = session.query(PestLog).order_by(PestLog.date.desc())
    if resolved is not None:
        query = query.filter(PestLog.resolved == resolved)
    return query.all()


@router.post("/", response_model=PestLogRead, status_code=201)
def create_pest_log(
    payload: PestLogCreate,
    session: Session = Depends(get_session),
) -> PestLog:
    if payload.plant_id is not None and not session.get(Plant, payload.plant_id):
        raise HTTPException(status_code=404, detail=f"Plant {payload.plant_id} not found")
    log = PestLog(
        date=payload.date.isoformat(),
        pest_name=payload.pest_name,
        plant_id=payload.plant_id,
        treatment=payload.treatment,
        notes=payload.notes,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.patch("/{pest_id}", response_model=PestLogRead)
def update_pest_log(
    pest_id: int,
    payload: dict,
    session: Session = Depends(get_session),
) -> PestLog:
    log = _get_or_404(session, pest_id)
    for key, value in payload.items():
        if hasattr(log, key) and key != "id":
            setattr(log, key, value)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.delete("/{pest_id}", status_code=204)
def delete_pest_log(
    pest_id: int,
    session: Session = Depends(get_session),
) -> None:
    log = _get_or_404(session, pest_id)
    session.delete(log)
    session.commit()
