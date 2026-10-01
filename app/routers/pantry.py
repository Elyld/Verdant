"""API router for post-harvest preservation log and pantry inventory."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Harvest, PantryItem, Plant, PreservationLog
from app.schemas import (
    PRESERVATION_METHODS,
    PantryItemCreate,
    PantryItemRead,
    PantryUse,
    PreservationCreate,
    PreservationRead,
)

router = APIRouter(prefix="/api/pantry", tags=["pantry"])

METHOD_LABELS = {
    "canned": "🥫 Canned",
    "frozen": "🧊 Frozen",
    "dehydrated": "☀️ Dehydrated",
    "fermented": "🫧 Fermented",
    "gave_away": "💝 Gave away",
    "fresh": "🥗 Ate fresh",
}


def _check_method(method: str) -> str:
    method = (method or "").strip().lower()
    if method not in PRESERVATION_METHODS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown method {method!r} (want one of: {', '.join(PRESERVATION_METHODS)}).",
        )
    return method


def _pres_or_404(session: Session, preservation_id: int) -> PreservationLog:
    log = session.get(PreservationLog, preservation_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"Preservation log {preservation_id} not found")
    return log


def _item_or_404(session: Session, item_id: int) -> PantryItem:
    item = session.get(PantryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Pantry item {item_id} not found")
    return item


# ------------------------------- preservation ------------------------------ #
@router.get("/preservation", response_model=List[PreservationRead])
def list_preservation(
    method: Optional[str] = Query(None, description="Filter by method"),
    session: Session = Depends(get_session),
) -> List[PreservationLog]:
    query = session.query(PreservationLog).order_by(
        PreservationLog.date.desc(), PreservationLog.id.desc()
    )
    if method:
        query = query.filter(PreservationLog.method == _check_method(method))
    return query.all()


@router.post("/preservation", response_model=PreservationRead, status_code=201)
def create_preservation(
    payload: PreservationCreate, session: Session = Depends(get_session)
) -> PreservationLog:
    method = _check_method(payload.method)
    if payload.plant_id is not None and not session.get(Plant, payload.plant_id):
        raise HTTPException(status_code=404, detail=f"Plant {payload.plant_id} not found")
    if payload.harvest_id is not None and not session.get(Harvest, payload.harvest_id):
        raise HTTPException(status_code=404, detail=f"Harvest {payload.harvest_id} not found")
    log = PreservationLog(
        date=payload.date.isoformat(),
        method=method,
        variety_name=payload.variety_name.strip(),
        plant_id=payload.plant_id,
        harvest_id=payload.harvest_id,
        qty_in=payload.qty_in,
        qty_in_unit=payload.qty_in_unit.strip(),
        qty_out=payload.qty_out,
        qty_out_unit=payload.qty_out_unit.strip(),
        stored_location=payload.stored_location.strip(),
        notes=payload.notes,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    if payload.add_to_pantry and (payload.qty_out or 0) > 0:
        name = payload.pantry_name.strip() or (
            f"{METHOD_LABELS.get(method, method)} {log.variety_name}".strip() or "Pantry item"
        )
        session.add(
            PantryItem(
                name=name,
                method=method,
                quantity=payload.qty_out or 0,
                unit=payload.qty_out_unit.strip(),
                stored_date=log.date,
                location=log.stored_location or "",
                preservation_id=log.id,
            )
        )
        session.commit()
    return log


@router.delete("/preservation/{preservation_id}", status_code=204)
def delete_preservation(preservation_id: int, session: Session = Depends(get_session)) -> None:
    log = _pres_or_404(session, preservation_id)
    # Pantry items spawned from this log keep their history; just unlink them.
    for item in session.query(PantryItem).filter(PantryItem.preservation_id == log.id).all():
        item.preservation_id = None
    session.delete(log)
    session.commit()


# --------------------------------- pantry ---------------------------------- #
@router.get("/items", response_model=List[PantryItemRead])
def list_pantry_items(
    method: Optional[str] = Query(None, description="Filter by method"),
    session: Session = Depends(get_session),
) -> List[PantryItem]:
    query = session.query(PantryItem).order_by(
        PantryItem.stored_date.desc(), PantryItem.id.desc()
    )
    if method:
        query = query.filter(PantryItem.method == _check_method(method))
    return query.all()


@router.post("/items", response_model=PantryItemRead, status_code=201)
def create_pantry_item(
    payload: PantryItemCreate, session: Session = Depends(get_session)
) -> PantryItem:
    method = _check_method(payload.method) if payload.method else ""
    item = PantryItem(
        name=payload.name.strip(),
        method=method,
        quantity=payload.quantity,
        unit=payload.unit.strip(),
        stored_date=payload.stored_date.isoformat(),
        location=payload.location.strip(),
        notes=payload.notes,
        preservation_id=payload.preservation_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.post("/items/{item_id}/use", response_model=PantryItemRead)
def use_pantry_item(
    item_id: int, payload: PantryUse, session: Session = Depends(get_session)
) -> PantryItem:
    """Decrement a pantry item; empties (≤ 0) are removed, history stays in the log."""
    item = _item_or_404(session, item_id)
    item.quantity = round((item.quantity or 0) - payload.amount, 4)
    if item.quantity <= 0:
        tombstone = PantryItemRead(
            id=item.id, name=item.name, method=item.method or "", quantity=0,
            unit=item.unit or "", stored_date=item.stored_date or "1970-01-01",
        )
        session.delete(item)
        session.commit()
        return tombstone
    session.commit()
    session.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=204)
def delete_pantry_item(item_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_item_or_404(session, item_id))
    session.commit()
