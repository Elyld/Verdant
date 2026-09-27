"""API router for the seed packet catalog (the seed stash inventory)."""
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import AlbumImage, SeedPacket, SeedSource, apply_patch
from app.storage import copy_stored, delete_stored, save_upload

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


def _check_vendor_id(session, vendor_id):
    if vendor_id is not None and not session.get(SeedSource, vendor_id):
        raise HTTPException(404, f"Seed source {vendor_id} not found")


def _coerce_optional_int(value, field_name: str, minimum: int = None):
    """Coerce a raw JSON int field; "" counts as unset, garbage 422s."""
    if value in (None, ""):
        return None
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        raise HTTPException(422, f"{field_name} {value!r} is not a whole number.")
    if minimum is not None and ivalue < minimum:
        raise HTTPException(422, f"{field_name} cannot be less than {minimum}.")
    return ivalue


@router.post("/", response_model=SeedPacket, status_code=201)
def create_packet(payload: dict, session: Session = Depends(get_session)) -> SeedPacket:
    if not (payload.get("variety_name") or "").strip():
        raise HTTPException(status_code=422, detail="variety_name is required")
    _check_vendor_id(session, payload.get("vendor_id"))
    packet = SeedPacket(
        variety_name=payload["variety_name"].strip(),
        species_type=(payload.get("species_type") or "").strip(),
        category=(payload.get("category") or "").strip(),
        vendor_id=payload.get("vendor_id"),
        vendor_name=(payload.get("vendor_name") or "").strip(),
        vendor_url=_normalize_url(payload.get("vendor_url") or ""),
        year_acquired=_coerce_optional_int(payload.get("year_acquired"), "year_acquired"),
        quantity=(payload.get("quantity") or "").strip(),
        seed_count=_coerce_optional_int(payload.get("seed_count"), "seed_count", minimum=0),
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
    payload = dict(payload)
    for key in ("seed_count",):
        if key in payload:
            payload[key] = _coerce_optional_int(payload[key], key, minimum=0)
    if "year_acquired" in payload:
        payload["year_acquired"] = _coerce_optional_int(payload["year_acquired"], "year_acquired")
    if "vendor_id" in payload:
        _check_vendor_id(session, payload["vendor_id"])
    # packet_id is the stable public ID; photo paths are managed exclusively
    # by the /photo upload endpoints — none are rewritable here.
    apply_patch(packet, payload, exclude=("packet_id", "photo_path", "photo_back_path"))
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


class LibraryPhotoAttach(BaseModel):
    image_id: int
    side: str = Field(default="front", pattern="^(front|back)$")


@router.post("/{packet_id}/photo-from-library", response_model=SeedPacket)
def attach_library_photo(
    packet_id: int,
    body: LibraryPhotoAttach,
    session: Session = Depends(get_session),
) -> SeedPacket:
    """Set a packet's front/back photo from an existing library photo.

    The library image is *copied* into the packet's own storage folder, so
    replacing or deleting the packet photo never touches the original
    (e.g. the Immich album import it came from).
    """
    packet = _get_or_404(session, packet_id)
    img = session.get(AlbumImage, body.image_id)
    if not img:
        raise HTTPException(
            status_code=404, detail=f"Library photo {body.image_id} not found"
        )
    attr = "photo_path" if body.side == "front" else "photo_back_path"
    if getattr(packet, attr):
        delete_stored(getattr(packet, attr))
    setattr(packet, attr, copy_stored(img.file_path, f"seed-packets/{packet.id}"))
    session.add(packet)
    session.commit()
    session.refresh(packet)
    return packet
