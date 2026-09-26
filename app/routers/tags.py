"""API router for NFC garden tags."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import GardenTag, utcnow

router = APIRouter(prefix="/api/tags", tags=["tags"])

# action -> (path template, which target field it uses)
# {id} is filled from target_id, {text} from target_text (URL-encoded by the client).
TAG_DESTINATIONS = {
    "plant": "/plants?plant={id}",
    "quick_plant": "/quick?plant={id}",
    "fertilize": "/observations?fertilizer={id}",
    "pest": "/pests?product={text}",
    "harvest": "/quick?action=harvest&plant={id}",
    "harvest_any": "/quick?action=harvest",
    "location": "/quick?location={id}",
    "seed_add": "/seeds?tab=catalog&add=1",
    "water": "/quick?action=water&location={id}",
}


def tag_destination(tag: GardenTag) -> str:
    template = TAG_DESTINATIONS.get(tag.action, "/quick")
    return template.format(id=tag.target_id or "", text=tag.target_text or "")


def _get_or_404(session: Session, tag_id: int) -> GardenTag:
    tag = session.get(GardenTag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")
    return tag


@router.get("/", response_model=List[GardenTag])
def list_tags(
    q: Optional[str] = Query(None, description="Search labels"),
    session: Session = Depends(get_session),
) -> List[GardenTag]:
    query = session.query(GardenTag).order_by(GardenTag.label)
    if q:
        query = query.filter(GardenTag.label.ilike(f"%{q}%"))
    return query.all()


@router.post("/", response_model=GardenTag, status_code=201)
def create_tag(payload: dict, session: Session = Depends(get_session)) -> GardenTag:
    label = (payload.get("label") or "").strip()
    action = (payload.get("action") or "").strip()
    if not label:
        raise HTTPException(status_code=422, detail="label is required")
    if action not in TAG_DESTINATIONS:
        raise HTTPException(
            status_code=422,
            detail=f"unknown action '{action}'; expected one of {sorted(TAG_DESTINATIONS)}",
        )
    tag = GardenTag(
        label=label,
        action=action,
        target_id=payload.get("target_id"),
        target_text=(payload.get("target_text") or "").strip(),
    )
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


@router.get("/{tag_id}", response_model=GardenTag)
def get_tag(tag_id: int, session: Session = Depends(get_session)) -> GardenTag:
    return _get_or_404(session, tag_id)


@router.patch("/{tag_id}", response_model=GardenTag)
def update_tag(
    tag_id: int, payload: dict, session: Session = Depends(get_session)
) -> GardenTag:
    tag = _get_or_404(session, tag_id)
    if "action" in payload and payload["action"] not in TAG_DESTINATIONS:
        raise HTTPException(status_code=422, detail=f"unknown action '{payload['action']}'")
    for key, value in payload.items():
        if hasattr(tag, key) and key not in ("id", "code", "tap_count", "last_tapped_at", "created_at"):
            setattr(tag, key, value)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get_or_404(session, tag_id))
    session.commit()


@router.post("/{tag_id}/tap", response_model=GardenTag)
def record_tap(tag_id: int, session: Session = Depends(get_session)) -> GardenTag:
    tag = _get_or_404(session, tag_id)
    tag.tap_count += 1
    tag.last_tapped_at = utcnow()
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag
