"""Albums: imported photo collections (upload or from URL) + import helpers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import Album, AlbumImage
from app.schemas import (
    AlbumCreateResult,
    AlbumImportFromAlbum,
    AlbumRead,
    AlbumImageRef,
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
