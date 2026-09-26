"""Import photos/albums directly from a self-hosted Immich instance.

This never writes to Immich; it only reads albums/assets and copies bytes
into a local `Album`/`AlbumImage` (the same tables the URL-import feature
uses), so the existing "Pull from album" picker on the New Entry form works
unchanged for Immich-sourced photos too.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app import immich
from app.database import UPLOAD_DIR, get_session
from app.models import Album, AlbumImage
from app.schemas import ImmichBatchImportResult
from app.storage import ALLOWED_TYPES, _sniff

router = APIRouter(prefix="/api/immich", tags=["immich"])

log = logging.getLogger("verdant.immich")

BATCH_DEFAULT = 50
BATCH_MAX = 200


def _parse_dt(value) -> Optional[datetime]:
    """Parse an Immich ISO timestamp to naive UTC (matches utcnow storage)."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _as_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _tag_names(value) -> str:
    """Immich asset ``tags`` -> comma-separated names.

    Immich ingests XMP sidecar keywords as tags, so sideloaded XMP data
    arrives here. Handles both ``[{"name": ...}]`` and plain strings.
    """
    names: List[str] = []
    for tag in value or []:
        if isinstance(tag, dict):
            name = tag.get("name") or tag.get("value")
        else:
            name = tag
        name = str(name).strip() if name is not None else ""
        if name:
            names.append(name)
    seen, out = set(), []
    for name in names:
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return ", ".join(out)[:500]


def _asset_metadata(asset: dict) -> dict:
    """Pull the photo metadata we keep out of an Immich asset dict."""
    exif = asset.get("exifInfo") or {}
    return {
        "taken_at": _parse_dt(exif.get("dateTimeOriginal") or asset.get("fileCreatedAt")),
        "camera_make": (exif.get("make") or "").strip()[:100],
        "camera_model": (exif.get("model") or "").strip()[:100],
        "latitude": _as_float(exif.get("latitude")),
        "longitude": _as_float(exif.get("longitude")),
        "tags": _tag_names(asset.get("tags")),
    }


class ImmichAlbumSummary(BaseModel):
    id: str
    albumName: str
    assetCount: int


class ImmichImportRequest(BaseModel):
    album_id: str


@router.get("/status")
def immich_status() -> dict:
    """Whether Immich is configured, without leaking the API key."""
    import os

    configured = bool(os.getenv("IMMICH_BASE_URL")) and bool(os.getenv("IMMICH_API_KEY"))
    return {"configured": configured}


@router.get("/albums", response_model=List[ImmichAlbumSummary])
def list_immich_albums() -> List[dict]:
    albums = immich.list_albums()
    return [
        {
            "id": a.get("id"),
            "albumName": a.get("albumName", "Untitled"),
            "assetCount": a.get("assetCount", len(a.get("assets", []) or [])),
        }
        for a in albums
    ]


@router.post("/albums/{immich_album_id}/import", response_model=ImmichBatchImportResult)
def import_immich_album(
    immich_album_id: str,
    offset: int = 0,
    limit: int = BATCH_DEFAULT,
    album_id: Optional[int] = None,
    session: Session = Depends(get_session),
) -> ImmichBatchImportResult:
    """Copy one batch of photo assets from an Immich album into a local Album.

    The frontend calls this repeatedly with increasing ``offset`` until
    ``done`` is true, so albums of any size import without hitting request
    timeouts. Batches are idempotent: assets already imported (matched by
    ``source_url``) are skipped, so a retried batch never creates dupes.
    """
    if offset < 0 or limit < 1 or limit > BATCH_MAX:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"offset must be >= 0 and 1 <= limit <= {BATCH_MAX}",
        )
    remote = immich.get_album(immich_album_id)
    assets = immich.list_album_assets(immich_album_id)
    photos = [a for a in assets if a.get("type") in (None, "IMAGE")]
    total = len(photos)
    if total == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That Immich album has no assets.")

    if album_id is None:
        if offset != 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="album_id is required when offset > 0",
            )
        # Re-importing the same Immich album must land in the existing local
        # album, not create a duplicate (Plants 2025 x3). The per-asset skip
        # below keeps it idempotent.
        source = f"immich:{immich_album_id}"
        album = session.exec(select(Album).where(Album.source_url == source)).first()
        if album is not None:
            remote_name = remote.get("albumName") or "Immich import"
            if album.name != remote_name:
                album.name = remote_name
                session.add(album)
                session.commit()
        else:
            album = Album(
                name=remote.get("albumName") or "Immich import",
                source_url=source,
            )
            session.add(album)
            session.commit()
            session.refresh(album)
    else:
        album = session.get(Album, album_id)
        if album is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Local album not found.")

    target_dir = UPLOAD_DIR / f"albums/{album.id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    already = set(
        session.exec(
            select(AlbumImage.source_url).where(AlbumImage.album_id == album.id)
        ).all()
    )

    created = 0
    errors: List[str] = []
    for asset in photos[offset : offset + limit]:
        asset_id = asset.get("id")
        source = f"immich:{asset_id}"
        if source in already:
            continue  # retried batch: skip, no dupes
        original_name = asset.get("originalFileName", "") or ""
        try:
            data = immich.download_asset(asset_id)
        except HTTPException as exc:
            errors.append(f"{original_name or asset_id}: {exc.detail}")
            continue

        kind = _sniff(data[:32])
        if kind not in ALLOWED_TYPES:
            errors.append(f"{original_name or asset_id}: not a supported image type")
            continue

        fname = f"{secrets.token_hex(16)}{ALLOWED_TYPES[kind]}"
        (target_dir / fname).write_bytes(data)
        meta = _asset_metadata(asset)
        session.add(
            AlbumImage(
                album_id=album.id,
                file_path=f"/uploads/albums/{album.id}/{fname}",
                title=original_name[:200],
                original_name=original_name[:200],
                source_url=source,
                taken_at=meta["taken_at"],
                camera_make=meta["camera_make"],
                camera_model=meta["camera_model"],
                latitude=meta["latitude"],
                longitude=meta["longitude"],
                tags=meta["tags"],
            )
        )
        already.add(source)
        created += 1

    session.commit()
    session.refresh(album)
    if errors:
        # Per-asset failures used to be invisible (the UI only showed the
        # created count), so log them where `docker logs` can see them.
        log.warning(
            "Immich import batch (album %s, offset %d): %d failed, %d created. First errors: %s",
            immich_album_id,
            offset,
            len(errors),
            created,
            "; ".join(errors[:5]),
        )
    done = offset + limit >= total
    return ImmichBatchImportResult(
        album_id=album.id,
        album_name=album.name,
        total=total,
        imported=len(album.images),
        done=done,
        created=created,
        failed=len(errors),
        errors=errors[:10],
    )
