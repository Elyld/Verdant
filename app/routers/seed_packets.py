"""API router for the seed packet catalog (the seed stash inventory)."""
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import SeedPacket, SeedSource
from app.storage import delete_stored, save_upload

router = APIRouter(prefix="/api/seed-packets", tags=["seed-packets"])


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url and "://" not in url:
        url = "https://" + url.lstrip("/")
    return url


def _split_source_notes(notes: str):
    """Pull the import-folded URL / acquired-year lines out of seed-source notes.

    The CSV importer folds 'Contact / URL' and 'Year Acquired' into notes as
    'URL: ...' / 'Acquired: ...' lines; the stash wants them as real fields.
    Returns (vendor_url, year_acquired, remaining_notes_lines).
    """
    url, year, rest = "", None, []
    for line in (notes or "").splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("url:"):
            url = _normalize_url(s[4:].strip()) or url
        elif low.startswith("acquired:"):
            m = re.search(r"\d{4}", s)
            if m:
                year = int(m.group())
            else:
                rest.append(line)
        else:
            rest.append(line)
    return url, year, rest


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
        vendor_name=(payload.get("vendor_name") or "").strip(),
        vendor_url=_normalize_url(payload.get("vendor_url") or ""),
        year_acquired=payload.get("year_acquired"),
        quantity=(payload.get("quantity") or "").strip(),
        seed_count=payload.get("seed_count"),
        notes=(payload.get("notes") or "").strip() or None,
        date_added=payload.get("date_added") or "",
    )
    session.add(packet)
    session.commit()
    session.refresh(packet)
    return packet


@router.get("/vendors", response_model=List[str])
def distinct_vendor_names(session: Session = Depends(get_session)) -> List[str]:
    """Every vendor name used on a packet, once each — for the autocomplete."""
    rows = session.query(SeedPacket.vendor_name).distinct().order_by(SeedPacket.vendor_name).all()
    # legacy session.query returns one-tuple rows for a single column
    return sorted({str(row[0]).strip() for row in rows if row[0] and str(row[0]).strip()})


@router.post("/from-sources", status_code=201)
def convert_from_sources(session: Session = Depends(get_session)) -> dict:
    """Move seed sources into the stash: one packet per source row.

    Idempotent — a source whose (variety, vendor) already exists as a packet
    is skipped, so re-running never creates dupes.
    """
    sources = session.query(SeedSource).order_by(SeedSource.source, SeedSource.variety).all()
    created, skipped = 0, 0
    for src in sources:
        variety = (src.variety or "").strip() or "Unknown variety"
        vendor = (src.source or "").strip()
        exists = (
            session.query(SeedPacket)
            .filter(SeedPacket.variety_name == variety, SeedPacket.vendor_name == vendor)
            .first()
        )
        if exists:
            skipped += 1
            continue
        url, year, rest = _split_source_notes(src.notes or "")
        session.add(
            SeedPacket(
                variety_name=variety,
                vendor_name=vendor,
                vendor_url=url,
                year_acquired=year,
                notes="\n".join(rest).strip() or None,
            )
        )
        created += 1
    session.commit()
    return {"created": created, "skipped": skipped, "total": len(sources)}


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
    if packet.photo_back_path:
        delete_stored(packet.photo_back_path)
    session.delete(packet)
    session.commit()


@router.post("/{packet_id}/photo", response_model=SeedPacket)
async def upload_packet_photo(
    packet_id: int,
    file: UploadFile = File(...),
    side: str = Query(default="front", pattern="^(front|back)$"),
    session: Session = Depends(get_session),
) -> SeedPacket:
    packet = _get_or_404(session, packet_id)
    attr = "photo_path" if side == "front" else "photo_back_path"
    if getattr(packet, attr):
        delete_stored(getattr(packet, attr))
    setattr(packet, attr, await save_upload(file, f"seed-packets/{packet.id}"))
    session.add(packet)
    session.commit()
    session.refresh(packet)
    return packet
