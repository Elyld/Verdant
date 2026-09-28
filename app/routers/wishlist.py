"""API router for the seed wishlist — varieties to buy on the next winter order.

Wishlist items stand apart from the stash (SeedPacket): they are varieties
the gardener does *not* have on hand and is considering ordering. Each row
carries a ``checked`` flag so the winter order assistant can present a
tick-what-you-want list, and the assistant resolves the last vendor/date
for each variety from past invoices.
"""
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlmodel import select

from app.database import get_session
from app.models import WishlistItem, apply_patch

router = APIRouter(prefix="/api/wishlist", tags=["wishlist"])


def _get_or_404(session: Session, item_id: int) -> WishlistItem:
    item = session.get(WishlistItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Wishlist item {item_id} not found")
    return item


@router.get("/", response_model=List[WishlistItem])
def list_wishlist(session: Session = Depends(get_session)) -> List[WishlistItem]:
    return session.exec(select(WishlistItem).order_by(WishlistItem.id)).all()


@router.post("/", response_model=WishlistItem, status_code=201)
def create_wishlist_item(payload: dict, session: Session = Depends(get_session)) -> WishlistItem:
    variety = (payload.get("variety_name") or "").strip()
    if not variety:
        raise HTTPException(status_code=422, detail="variety_name is required")
    item = WishlistItem(
        variety_name=variety,
        vendor_name=(payload.get("vendor_name") or "").strip(),
        notes=(payload.get("notes") or "").strip() or None,
        checked=bool(payload.get("checked", False)),
        date_added=date.today().isoformat(),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/{item_id}", response_model=WishlistItem)
def update_wishlist_item(
    item_id: int, payload: dict, session: Session = Depends(get_session)
) -> WishlistItem:
    item = _get_or_404(session, item_id)
    apply_patch(item, dict(payload), exclude=("date_added",))
    if not item.variety_name or not item.variety_name.strip():
        raise HTTPException(status_code=422, detail="variety_name is required")
    item.variety_name = item.variety_name.strip()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_wishlist_item(item_id: int, session: Session = Depends(get_session)) -> None:
    item = _get_or_404(session, item_id)
    session.delete(item)
    session.commit()
