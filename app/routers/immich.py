"""Import photos/albums directly from a self-hosted Immich instance.

This never writes to Immich; it only reads albums/assets and copies bytes
into a local `Album`/`AlbumImage` (the same tables the URL-import feature
uses), so the existing "Pull from album" picker on the New Entry form works
unchanged for Immich-sourced photos too.
"""
from __future__ import annotations

import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from app import immich
from app.database import UPLOAD_DIR, get_session
from app.models import Album, AlbumImage
from app.schemas import AlbumCreateResult, AlbumRead
from app.storage import ALLOWED_TYPES, _sniff

router = APIRouter(prefix="/api/immich", tags=["immich"])

MAX_ASSETS = 200


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


@router.post("/albums/{immich_album_id}/import", response_model=AlbumCreateResult, status_code=status.HTTP_201_CREATED)
def import_immich_album(
    immich_album_id: str,
    session: Session = Depends(get_session),
) -> AlbumCreateResult:
    """Copy every photo asset from an Immich album into a new local Album."""
    remote = immich.get_album(immich_album_id)
    assets = remote.get("assets", []) or []
    if not assets:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That Immich album has no assets.")
    if len(assets) > MAX_ASSETS:
        assets = assets[:MAX_ASSETS]

    name = remote.get("albumName") or "Immich import"
    album = Album(name=name)
    session.add(album)
    session.commit()
    session.refresh(album)

    created = 0
    errors: List[str] = []
    target_dir = UPLOAD_DIR / f"albums/{album.id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    for asset in assets:
        asset_id = asset.get("id")
        original_name = asset.get("originalFileName", "") or ""
        if asset.get("type") not in (None, "IMAGE"):
            continue  # skip videos, etc.
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
        session.add(
            AlbumImage(
                album_id=album.id,
                file_path=f"/uploads/albums/{album.id}/{fname}",
                title=original_name[:200],
                original_name=original_name[:200],
                source_url=f"immich:{asset_id}",
            )
        )
        created += 1

    session.add(album)
    session.commit()
    session.refresh(album)
    return AlbumCreateResult(album=album, created=created, failed=len(errors), errors=errors[:10])
