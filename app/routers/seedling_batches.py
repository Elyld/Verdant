"""API router for indoor seedling batches — the seed-starting workstation."""
from datetime import date as Date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import SeedlingBatch

router = APIRouter(prefix="/api/seedling-batches", tags=["seedling-batches"])

STATUSES = ["sowing", "germinating", "growing", "hardening", "transplanted", "finished", "failed"]
ACTIVE = ["sowing", "germinating", "growing", "hardening"]
NEXT_STATUS = {
    "sowing": "germinating",
    "germinating": "growing",
    "growing": "hardening",
    "hardening": "transplanted",
    "transplanted": "finished",
}

STATUS_LABELS = {
    "sowing": "🌱 Sowing",
    "germinating": "🌤️ Germinating",
    "growing": "🌿 Growing",
    "hardening": "💨 Hardening off",
    "transplanted": "🪴 Transplanted",
    "finished": "✅ Finished",
    "failed": "❌ Failed",
}


def _get_or_404(session: Session, batch_id: int) -> SeedlingBatch:
    batch = session.get(SeedlingBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Seedling batch {batch_id} not found")
    return batch


def _check_status(status: str) -> str:
    status = (status or "").strip().lower()
    if status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of: {', '.join(STATUSES)}")
    return status


@router.get("/", response_model=List[SeedlingBatch])
def list_batches(
    status: Optional[str] = Query(None, description="Filter by status"),
    active: Optional[bool] = Query(None, description="Only active (not finished/failed) batches"),
    session: Session = Depends(get_session),
) -> List[SeedlingBatch]:
    query = session.query(SeedlingBatch)
    if status:
        query = query.filter(SeedlingBatch.status == _check_status(status))
    if active:
        query = query.filter(SeedlingBatch.status.in_(ACTIVE))
    return query.order_by(SeedlingBatch.sow_date.desc(), SeedlingBatch.id.desc()).all()


@router.post("/", response_model=SeedlingBatch, status_code=201)
def create_batch(payload: dict, session: Session = Depends(get_session)) -> SeedlingBatch:
    variety = (payload.get("variety_name") or "").strip()
    if not variety:
        raise HTTPException(status_code=422, detail="variety_name is required")
    batch = SeedlingBatch(
        variety_name=variety,
        packet_id=payload.get("packet_id"),
        sow_date=(payload.get("sow_date") or "").strip() or Date.today().isoformat(),
        tray=(payload.get("tray") or "").strip(),
        location=(payload.get("location") or "").strip(),
        heat_mat=bool(payload.get("heat_mat")),
        grow_light=(payload.get("grow_light") or "").strip(),
        cells_sown=payload.get("cells_sown"),
        status=_check_status(payload.get("status") or "sowing"),
        notes=(payload.get("notes") or "").strip(),
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


@router.get("/{batch_id}", response_model=SeedlingBatch)
def get_batch(batch_id: int, session: Session = Depends(get_session)) -> SeedlingBatch:
    return _get_or_404(session, batch_id)


@router.patch("/{batch_id}", response_model=SeedlingBatch)
def update_batch(batch_id: int, payload: dict, session: Session = Depends(get_session)) -> SeedlingBatch:
    batch = _get_or_404(session, batch_id)
    for key, value in payload.items():
        if key in ("id", "batch_id"):
            continue
        if hasattr(batch, key):
            if key == "status":
                value = _check_status(value)
            setattr(batch, key, value)
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


@router.post("/{batch_id}/sprout", response_model=SeedlingBatch)
def log_sprout(
    batch_id: int,
    count: int = Query(default=1, ge=1, description="Newly sprouted seedlings"),
    session: Session = Depends(get_session),
) -> SeedlingBatch:
    """One-tap germination logging: add sprouted seedlings; stamps the first-sprout date."""
    batch = _get_or_404(session, batch_id)
    batch.germinated = (batch.germinated or 0) + count
    if not batch.germination_date:
        batch.germination_date = Date.today().isoformat()
    if batch.status == "sowing":
        batch.status = "germinating"
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


@router.post("/{batch_id}/advance", response_model=SeedlingBatch)
def advance_batch(batch_id: int, session: Session = Depends(get_session)) -> SeedlingBatch:
    """Move a batch to the next stage; stamps the transplant date on the way out."""
    batch = _get_or_404(session, batch_id)
    nxt = NEXT_STATUS.get(batch.status)
    if not nxt:
        raise HTTPException(status_code=409, detail=f"Batch is {batch.status}; nothing to advance to")
    batch.status = nxt
    if nxt == "transplanted" and not batch.transplant_date:
        batch.transplant_date = Date.today().isoformat()
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


@router.delete("/{batch_id}", status_code=204)
def delete_batch(batch_id: int, session: Session = Depends(get_session)) -> None:
    batch = _get_or_404(session, batch_id)
    session.delete(batch)
    session.commit()
