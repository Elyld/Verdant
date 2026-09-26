"""Albums: imported photo collections (upload or from URL) + import helpers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import Album, AlbumImage, Plant
from app.routers.immich import _asset_metadata
from app import immich as immich_client
from app.schemas import (
    AlbumCreateResult,
    AlbumImportFromAlbum,
    AlbumMergeResult,
    AlbumMetadataSyncResult,
    AlbumRead,
    AlbumImageRead,
    AlbumImageRef,
    ImageAssignRequest,
    ImageBulkAssignRequest,
    ImportFromUrlRequest,
)
from app.storage import delete_stored, save_uploads

router = APIRouter(tags=["albums"])

MAX_URLS = 25
ALLOWED_URL_SCHEMES = ("http", "https")


def _base_url(raw: str) -> str:
    u = (raw or "").strip().rstrip("/")
    if not u:
        u = "http://localhost"
    try:
        from urllib.parse import urlparse

        parsed = urlparse(u)
    except Exception:
        return "http://localhost"
    if not parsed.netloc:
        return "http://localhost"
    return f"{parsed.scheme}://{parsed.netloc}"


def _resolve_image_path(file_path: str) -> Optional[Path]:
    prefix = "/uploads/"
    if not file_path.startswith(prefix):
        return None
    from app.database import UPLOAD_DIR

    candidate = (UPLOAD_DIR / file_path[len(prefix):]).resolve()
    root = UPLOAD_DIR.resolve()
    if root != candidate and root not in candidate.parents:
        return None
    return candidate


@router.get("/api/albums", response_model=List[AlbumRead])
def list_albums(session: Session = Depends(get_session)) -> List[Album]:
    return list(session.exec(select(Album).order_by(Album.created_at.desc(), Album.id.desc())).all())


@router.post(
    "/api/albums",
    response_model=AlbumCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_album(
    name: str = Form(..., min_length=1, max_length=120),
    files: Optional[List[UploadFile]] = File(default=None),
    session: Session = Depends(get_session),
) -> AlbumCreateResult:
    """Create an album and import the given files into it.

    A request with no files is fine: it creates an empty album that can be
    filled later with "Import from URL" or "Add photos" buttons.
    """
    album = Album(name=name.strip())
    session.add(album)
    session.commit()
    session.refresh(album)

    created = 0
    if files:
        try:
            urls = await save_uploads(files, f"albums/{album.id}")
        except HTTPException:
            session.delete(album)
            session.commit()
            raise
        except Exception:
            session.delete(album)
            session.commit()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Import failed")
        for url in urls:
            session.add(AlbumImage(album_id=album.id, file_path=url))
            created += 1
        session.add(album)
        session.commit()
        session.refresh(album)

    return AlbumCreateResult(album=album, created=created, failed=0)


@router.get("/api/albums/{album_id}", response_model=AlbumRead)
def get_album(album_id: int, session: Session = Depends(get_session)) -> Album:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    return album


@router.post("/api/albums/{album_id}/sync-metadata", response_model=AlbumMetadataSyncResult)
def sync_album_metadata(album_id: int, session: Session = Depends(get_session)) -> AlbumMetadataSyncResult:
    """Backfill photo metadata (date taken, camera, GPS, XMP tags) from Immich.

    Only fills blank fields — never overwrites. Meant for photos imported
    before metadata capture existed.
    """
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    if not (album.source_url or "").startswith("immich:"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only Immich-imported albums can sync metadata.",
        )
    immich_album_id = album.source_url.split(":", 1)[1]
    assets = immich_client.list_album_assets(immich_album_id)
    by_source = {f"immich:{a.get('id')}": a for a in assets if a.get("id")}
    updated = 0
    for img in album.images:
        asset = by_source.get(img.source_url)
        if asset is None:
            continue
        meta = _asset_metadata(asset)
        changed = False
        if meta["taken_at"] is not None and img.taken_at is None:
            img.taken_at = meta["taken_at"]
            changed = True
        if meta["camera_make"] and not img.camera_make:
            img.camera_make = meta["camera_make"]
            changed = True
        if meta["camera_model"] and not img.camera_model:
            img.camera_model = meta["camera_model"]
            changed = True
        if meta["latitude"] is not None and img.latitude is None:
            img.latitude = meta["latitude"]
            changed = True
        if meta["longitude"] is not None and img.longitude is None:
            img.longitude = meta["longitude"]
            changed = True
        if meta["tags"] and not img.tags:
            img.tags = meta["tags"]
            changed = True
        if changed:
            session.add(img)
            updated += 1
    session.commit()
    return AlbumMetadataSyncResult(album_id=album.id, total=len(album.images), updated=updated)


@router.post("/api/albums/merge-duplicates", response_model=AlbumMergeResult)
def merge_duplicate_albums(session: Session = Depends(get_session)) -> AlbumMergeResult:
    """Merge local albums imported from the same Immich album.

    Re-importing an album used to create a new local album each time
    ("Plants 2025" x3), so group by ``source_url`` and fold duplicates into
    the fullest album. Unique photos move over; byte-duplicate photos (same
    ``source_url`` as one the keeper already has) are dropped along with
    their files. Plant assignments move with the photos.
    """
    albums = session.exec(
        select(Album).where(Album.source_url != "").order_by(Album.id)
    ).all()
    groups: dict[str, list] = {}
    for album in albums:
        groups.setdefault(album.source_url, []).append(album)

    result = AlbumMergeResult(
        groups_merged=0, albums_removed=0, images_moved=0, files_removed=0
    )
    for source_url, dupes in groups.items():
        if len(dupes) < 2:
            continue
        counts = {a.id: len(a.images) for a in dupes}
        keeper = max(dupes, key=lambda a: (counts[a.id], -a.id))
        keeper_sources = {img.source_url for img in keeper.images if img.source_url}
        merged_names = []
        for dupe in dupes:
            if dupe.id == keeper.id:
                continue
            for img in list(dupe.images):
                if img.source_url and img.source_url in keeper_sources:
                    # True duplicate of a photo the keeper has: drop the row
                    # and its re-downloaded bytes.
                    delete_stored(img.file_path)
                    result.files_removed += 1
                    session.delete(img)
                else:
                    # Assign the relationship (not just album_id) so the photo
                    # leaves dupe.images — otherwise the cascade_delete on
                    # Album.images would take it down with the dupe album.
                    img.album = keeper
                    if img.source_url:
                        keeper_sources.add(img.source_url)
                    result.images_moved += 1
            merged_names.append(f"\u201C{dupe.name}\u201D ({counts[dupe.id]} photos)")
            session.delete(dupe)
            result.albums_removed += 1
        result.groups_merged += 1
        result.detail.append(
            f"Merged {', '.join(merged_names)} into \u201C{keeper.name}\u201D "
            f"({counts[keeper.id]} photos)."
        )
    session.commit()
    return result


@router.delete("/api/albums/{album_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_album(album_id: int, session: Session = Depends(get_session)) -> None:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    for img in album.images:
        delete_stored(img.file_path)
    session.delete(album)
    session.commit()


@router.post("/api/albums/{album_id}/import", response_model=AlbumCreateResult, status_code=status.HTTP_201_CREATED)
async def import_urls_into_album(
    album_id: int,
    payload: ImportFromUrlRequest,
    session: Session = Depends(get_session),
) -> AlbumCreateResult:
    """Download the given URLs and add them to this album."""
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    return await _import_urls(session, album, payload.urls)


@router.post("/api/import/urls", response_model=AlbumCreateResult, status_code=status.HTTP_201_CREATED)
async def import_urls(
    payload: ImportFromUrlRequest,
    session: Session = Depends(get_session),
) -> AlbumCreateResult:
    """Download the given URLs into an existing album (album_id) or a new 'Imported' album."""
    if payload.album_id is not None:
        album = session.get(Album, payload.album_id)
        if album is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    else:
        album = Album(name="Imported")
        session.add(album)
        session.commit()
        session.refresh(album)
    return await _import_urls(session, album, payload.urls)


async def _import_urls(
    session: Session, album: Album, urls: List[str]
) -> AlbumCreateResult:
    urls = [u.strip() for u in urls if u and u.strip()]
    if not urls:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No URLs provided")
    if len(urls) > MAX_URLS:
        raise HTTPException(status.HTTP_414_URI_TOO_LONG, detail=f"Max {MAX_URLS} URLs per import")

    errors: List[str] = []
    created = 0
    base = _base_url(os.getenv("GARDEN_PUBLIC_URL", ""))
    timeout = httpx.Timeout(20.0, connect=8.0)

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Verdant-Garden-Log"},
        base_url=base,
    ) as client:
        for url in urls:
            scheme = url.split("://", 1)[0].lower() if "://" in url else "http"
            if scheme not in ALLOWED_URL_SCHEMES:
                errors.append(f"Unsupported scheme in '{url[:80]}' (http/https only)")
                continue
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except Exception as exc:
                errors.append(f"Could not fetch '{url[:80]}': {exc.__class__.__name__}")
                continue
            data = resp.content
            if not data:
                errors.append(f"Empty response from '{url[:80]}'")
                continue
            if len(data) > 8 * 1024 * 1024:
                errors.append(f"'{url[:80]}' exceeds 8 MB")
                continue

            from app.storage import _sniff

            kind = _sniff(data[:32])
            if kind not in ("jpeg", "png", "gif", "webp", "bmp"):
                errors.append(f"'{url[:80]}' is not a supported image (jpg/png/gif/webp/bmp)")
                continue

            import secrets
            from app.database import UPLOAD_DIR
            from app.storage import ALLOWED_TYPES

            target_dir = UPLOAD_DIR / f"albums/{album.id}"
            target_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{secrets.token_hex(16)}{ALLOWED_TYPES[kind]}"
            (target_dir / fname).write_bytes(data)
            file_path = f"/uploads/albums/{album.id}/{fname}"

            last = url.rsplit("/", 1)[-1].split("?", 1)[0][:80]
            session.add(
                AlbumImage(
                    album_id=album.id,
                    file_path=file_path,
                    title=last,
                    original_name=last,
                    source_url=url[:500],
                )
            )
            created += 1

    session.add(album)
    session.commit()
    session.refresh(album)
    return AlbumCreateResult(album=album, created=created, failed=len(errors), errors=errors[:10])


@router.post("/api/posts/{post_id}/from-album", status_code=status.HTTP_201_CREATED)
def add_from_album(
    post_id: int,
    payload: AlbumImportFromAlbum,
    session: Session = Depends(get_session),
) -> int:
    """Copy the given album images into a post. Returns the number copied."""
    from app.models import Post, PostImage

    post = session.get(Post, post_id)
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Post not found")
    if not payload.image_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No images selected")

    copied = 0
    for image_id in payload.image_ids:
        album_img = session.get(AlbumImage, image_id)
        if album_img is None or album_img.album_id != payload.album_id:
            continue
        src = _resolve_image_path(album_img.file_path)
        if src is None or not src.exists():
            continue
        data = src.read_bytes()

        import secrets
        from app.database import UPLOAD_DIR
        from app.storage import _sniff, ALLOWED_TYPES

        kind = _sniff(data[:32])
        if kind is None:
            continue
        target_dir = UPLOAD_DIR / f"posts/{post.id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{secrets.token_hex(16)}{ALLOWED_TYPES[kind]}"
        (target_dir / fname).write_bytes(data)

        session.add(PostImage(post_id=post.id, file_path=f"/uploads/posts/{post.id}/{fname}"))
        copied += 1

    if not copied:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Selected images not found")
    from app.models import utcnow

    post.updated_at = utcnow()
    session.add(post)
    session.commit()
    return copied


# ---------------------------------------------------------------------------
# Photo <-> plant matching (the /match page)
# ---------------------------------------------------------------------------


def _image_read(img: AlbumImage, variety: Optional[str]) -> AlbumImageRead:
    read = AlbumImageRead.model_validate(img)
    read.plant_variety = variety
    return read


@router.get("/api/album-images/", response_model=List[AlbumImageRead])
def list_album_images(
    album_id: Optional[int] = None,
    plant_id: Optional[int] = None,
    unassigned_only: bool = False,
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> List[AlbumImageRead]:
    """List album photos, oldest-taken first, with their plant assignment.

    Filters: ``album_id``, ``plant_id`` (photos of one plant), or
    ``unassigned_only`` for the matching workflow.
    """
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    stmt = (
        select(AlbumImage, Plant.variety_name)
        .outerjoin(Plant, Plant.id == AlbumImage.plant_id)
        .order_by(
            AlbumImage.taken_at.is_(None),
            AlbumImage.taken_at,
            AlbumImage.id,
        )
        .limit(limit)
        .offset(offset)
    )
    if album_id is not None:
        stmt = stmt.where(AlbumImage.album_id == album_id)
    if plant_id is not None:
        stmt = stmt.where(AlbumImage.plant_id == plant_id)
    if unassigned_only:
        stmt = stmt.where(AlbumImage.plant_id.is_(None))
    rows = session.exec(stmt).all()
    return [_image_read(img, variety) for img, variety in rows]


@router.patch("/api/album-images/{image_id}", response_model=AlbumImageRead)
def assign_album_image(
    image_id: int,
    body: ImageAssignRequest,
    session: Session = Depends(get_session),
) -> AlbumImageRead:
    """Assign a photo to a plant (``plant_id: null`` unassigns it)."""
    img = session.get(AlbumImage, image_id)
    if img is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Photo not found")
    variety: Optional[str] = None
    if body.plant_id is not None:
        plant = session.get(Plant, body.plant_id)
        if plant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plant not found")
        variety = plant.variety_name
    img.plant_id = body.plant_id
    session.add(img)
    session.commit()
    session.refresh(img)
    return _image_read(img, variety)


@router.post("/api/album-images/bulk-assign")
def bulk_assign_album_images(
    body: ImageBulkAssignRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Assign many photos to one plant at once (``plant_id: null`` unassigns)."""
    if body.plant_id is not None and session.get(Plant, body.plant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plant not found")
    ids = list(dict.fromkeys(body.image_ids))
    images = session.exec(select(AlbumImage).where(AlbumImage.id.in_(ids))).all()
    for img in images:
        img.plant_id = body.plant_id
        session.add(img)
    session.commit()
    return {"updated": len(images)}
