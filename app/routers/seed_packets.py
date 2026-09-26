"""API router for the seed packet catalog (the seed stash inventory)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import SeedPacket
from app.storage import delete_stored, save_upload

router = APIRouter(prefix="/api/seed-packets", tags=["seed-packets"])


def _get_or_404(session: Session, packet_id: int) -> SeedPacket:
    packet = session.get(SeedPacket, packet_id)
    if not packet:
        raise HTTPException(status_code=404, detail=f"Seed packet {packet_id} not found")
    return packet


@router.get("/", response_model=List[SeedPacket])
def list_packets(
    q: Optional[str] = Query(None, description="Search variety / species / category"),
    category: Optional[str] = Query(None),
    session: Session = Depends(get_session),
) -> List[SeedPacket]:
    query = session.query(SeedPacket).order_by(SeedPacket.variety_name)
    if category:
        query = query.filter(SeedPacket.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (SeedPacket.variety_name.ilike(like))
            | (SeedPacket.species_type.ilike(like))
            | (SeedPacket.category.ilike(like))
        )
    return query.all()


@router.post("/", response_model=SeedPacket, status_code=201)
def create_packet(payload: dict, session: Session = Depends(get_session)) -> SeedPacket:
    if not (payload.get("variety_name") or "").strip():
        raise HTTPException(status_code=422, detail="variety_name is required")
    packet = SeedPacket(
        variety_name=payload["variety_name"].strip(),
        species_type=(payload.get("species_type") or "").strip(),
        category=(payload.get("category") or "").strip(),
        vendor_id=payload.get("vendor_id"),
        vendor_url=(payload.get("vendor_url") or "").strip(),
        year_acquired=payload.get("year_acquired"),
        quantity=(payload.get("quantity") or "").strip(),
        notes=(payload.get("notes") or "").strip() or None,
        date_added=payload.get("date_added") or "",
    )
    session.add(packet)
    session.commit()
    session.refresh(packet)
    return packet


@router.get("/{packet_id}", response_model=SeedPacket)
def get_packet(packet_id: int, session: Session = Depends(get_session)) -> SeedPacket:
    return _get_or_404(session, packet_id)


@router.patch("/{packet_id}", response_model=SeedPacket)
def update_packet(
    packet_id: int, payload: dict, session: Session = Depends(get_session)
) -> SeedPacket:
    packet = _get_or_404(session, packet_id)
    for key, value in payload.items():
        if hasattr(packet, key) and key not in ("id", "packet_id"):
            setattr(packet, key, value)
    session.add(packet)
    session.commit()
    session.refresh(packet)
    return packet


@router.delete("/{packet_id}", status_code=204)
def delete_packet(packet_id: int, session: Session = Depends(get_session)) -> None:
    packet = _get_or_404(session, packet_id)
    if packet.photo_path:
        delete_stored(packet.photo_path)
    session.delete(packet)
    session.commit()


@router.post("/{packet_id}/photo", response_model=SeedPacket)
async def upload_packet_photo(
    packet_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> SeedPacket:
    packet = _get_or_404(session, packet_id)
    if packet.photo_path:
        delete_stored(packet.photo_path)
    packet.photo_path = await save_upload(file, f"seed-packets/{packet.id}")
    session.add(packet)
    session.commit()
    session.refresh(packet)
    return packet
