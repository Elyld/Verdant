"""Albums: imported photo collections (upload or from URL) + import helpers."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.database import get_session
from app.models import Album, AlbumImage, Container, Plant, SeedPacket
from app.photo_dates import is_generated_filename, parse_filename_date
from app.routers.immich import _asset_metadata
from app import immich as immich_client
from app.schemas import (
    AlbumCreateResult,
    AlbumImportFromAlbum,
    AlbumMergeResult,
    AlbumMetadataSyncResult,
    AlbumPatchRequest,
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
    if not name.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Album name is required.")
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


@router.get("/api/albums/duplicate-names")
def duplicate_album_names(session: Session = Depends(get_session)) -> List[dict]:
    """Albums sharing a name (e.g. three "Plants 2025" from repeat imports).

    Drives the duplicate-name banner on the Photos page; the existing
    POST /api/albums/merge-duplicates folds same-source dupes together.
    Groups are by exact name, not by source album.
    """
    albums = session.exec(select(Album).order_by(Album.id)).all()
    groups: dict[str, list] = {}
    for album in albums:
        groups.setdefault(album.name, []).append(album)
    return [
        {
            "name": name,
            "album_ids": [a.id for a in dupes],
            "counts": [len(a.images) for a in dupes],
        }
        for name, dupes in groups.items()
        if len(dupes) > 1
    ]


@router.get("/api/albums/{album_id}/duplicate-shots")
def duplicate_shots(album_id: int, session: Session = Depends(get_session)) -> List[dict]:
    """Same-timestamp photo groups in one album (e.g. a low-res + full-res
    copy of the same shot). Reporting only — nothing is deleted or merged
    here; burst photos can share a timestamp legitimately, so a human
    decides what each group means."""
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    groups: dict = {}
    for img in album.images:
        if img.taken_at is None:
            continue
        groups.setdefault(img.taken_at, []).append(img)
    return [
        {
            "taken_at": taken.isoformat(),
            "image_ids": [i.id for i in imgs],
            "file_paths": [i.file_path for i in imgs],
        }
        for taken, imgs in sorted(groups.items())
        if len(imgs) > 1
    ]


@router.get("/api/albums/{album_id}", response_model=AlbumRead)
def get_album(album_id: int, session: Session = Depends(get_session)) -> Album:
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    return album


@router.patch("/api/albums/{album_id}", response_model=AlbumRead)
def update_album(
    album_id: int,
    body: AlbumPatchRequest,
    session: Session = Depends(get_session),
) -> Album:
    """Rename an album, or (re)point it at its Immich source.

    The source_url case is the adoption path for albums created before
    source tracking existed: stamping it here (or via an Immich import
    naming the album) is what makes sync-metadata work for them again.
    Only fields explicitly present change; source_url "" clears it.
    """
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    if "name" in body.model_fields_set:
        name = (body.name or "").strip()
        if not name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Album name is required.")
        album.name = name[:120]
    if "source_url" in body.model_fields_set:
        source = body.source_url or ""
        if source and not source.startswith("immich:"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="source_url must look like 'immich:<album-id>' (or be empty to clear it).",
            )
        album.source_url = source
    session.add(album)
    session.commit()
    session.refresh(album)
    return album


def _backfill_filename_dates(session: Session, album: Album) -> int:
    """Fill blank taken_at from photo filenames + flag generated names.

    Only fills blanks, never overwrites — the same rule as sync-metadata.
    Returns the number of images changed."""
    updated = 0
    for img in album.images:
        changed = False
        if img.taken_at is None:
            taken = parse_filename_date(img.original_name or img.title or "")
            if taken is not None:
                img.taken_at = taken
                changed = True
        if not img.is_generated and is_generated_filename(
            img.original_name or img.title or ""
        ):
            img.is_generated = True
            changed = True
        if changed:
            session.add(img)
            updated += 1
    return updated


@router.post("/api/albums/{album_id}/backfill-dates", response_model=AlbumMetadataSyncResult)
def backfill_album_dates(album_id: int, session: Session = Depends(get_session)) -> AlbumMetadataSyncResult:
    """Fill blank taken_at dates from photo filenames (no Immich needed).

    For legacy albums whose assets never carried a date: parses
    YYYYMMDD_HHMMSS and epoch-millis filenames, and flags chatgpt-* names
    as generated. Only fills blanks, never overwrites.
    """
    album = session.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album not found")
    updated = _backfill_filename_dates(session, album)
    session.commit()
    return AlbumMetadataSyncResult(album_id=album.id, total=len(album.images), updated=updated)


@router.post("/api/albums/{album_id}/sync-metadata", response_model=AlbumMetadataSyncResult)
def sync_album_metadata(album_id: int, session: Session = Depends(get_session)) -> AlbumMetadataSyncResult:
    """Backfill photo metadata (date taken, camera, GPS, XMP tags) from Immich.

    Only fills blank fields — never overwrites. Meant for photos imported
    before metadata capture existed. Images still dateless after the Immich
    pass fall back to the date in their filename (same rule as
    backfill-dates), so legacy albums recover a chronology either way.
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
    updated += _backfill_filename_dates(session, album)
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

    # Albums with no source at all (created before source tracking) can
    # never join a source group above. Group those by exact name instead:
    # a same-name album whose photos are all already in a bigger same-name
    # album (compared by file content) is safe to drop; anything else is
    # reported and left alone, with the reason in `detail`.
    sourceless = session.exec(
        select(Album).where(
            or_(Album.source_url == "", Album.source_url.is_(None))
        ).order_by(Album.id)
    ).all()
    name_groups: dict[str, list] = {}
    for album in sourceless:
        name_groups.setdefault(album.name, []).append(album)
    saw_name_group = False
    removed_ids: set = set()
    for name, dupes in name_groups.items():
        if len(dupes) < 2:
            continue
        saw_name_group = True
        dupes.sort(key=lambda a: (len(a.images), a.id))
        group_resolved = False
        for candidate in list(dupes):
            if candidate.id in removed_ids:
                continue
            n_cand = len(candidate.images)
            cand_hashes, cand_unhashable = _album_content_hashes(candidate)
            if cand_unhashable:
                continue  # can't prove a subset with unreadable files
            for bigger in dupes:
                if bigger.id in removed_ids or bigger.id == candidate.id:
                    continue
                n_big = len(bigger.images)
                if n_big <= n_cand:
                    continue
                big_hashes, big_unhashable = _album_content_hashes(bigger)
                if big_unhashable:
                    continue
                if cand_hashes <= big_hashes:
                    for img in list(candidate.images):
                        delete_stored(img.file_path)
                        result.files_removed += 1
                    session.delete(candidate)
                    removed_ids.add(candidate.id)
                    result.albums_removed += 1
                    group_resolved = True
                    result.detail.append(
                        f"Removed \u201C{name}\u201D ({n_cand} photos) — "
                        f"every photo already in \u201C{bigger.name}\u201D "
                        f"({n_big} photos) by file content."
                    )
                    break
            else:
                shared = 0
                for other in dupes:
                    if other.id in removed_ids or other.id == candidate.id:
                        continue
                    other_hashes, _ = _album_content_hashes(other)
                    shared = max(shared, len(cand_hashes & other_hashes))
                if shared:
                    result.detail.append(
                        f"Albums named \u201C{name}\u201D share {shared} photos by content "
                        f"but neither contains the other — left alone."
                    )
                else:
                    result.detail.append(
                        f"Albums named \u201C{name}\u201D share no photos by content — left alone."
                    )
        if group_resolved:
            result.groups_merged += 1
    if result.groups_merged == 0 and result.albums_removed == 0 and not saw_name_group:
        result.detail.append(
            "No duplicates merged: no two albums share an Immich source or a name."
        )
    session.commit()
    return result


def _album_content_hashes(album: Album) -> tuple[set, int]:
    """(sha256 set, unhashable count) for an album's stored files.

    Unhashable means the file is missing or unreadable; such images can
    never support a strict-subset claim, so callers treat them conservatively.
    """
    hashes = set()
    unhashable = 0
    for img in album.images:
        path = _resolve_image_path(img.file_path)
        if path is None or not path.is_file():
            unhashable += 1
            continue
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 256), b""):
                    h.update(chunk)
            hashes.add(h.hexdigest())
        except OSError:
            unhashable += 1
    return hashes, unhashable


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

    # Re-running an import must not duplicate photos (the Immich importer
    # already skips on source_url; do the same here).
    already = set(
        session.exec(select(AlbumImage.source_url).where(AlbumImage.album_id == album.id)).all()
    )

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
            if url[:500] in already:
                continue  # already imported: skip, no dupes
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
                    taken_at=parse_filename_date(last),
                    is_generated=is_generated_filename(last),
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
# Photo <-> plant/packet/container matching (the /match page)
# ---------------------------------------------------------------------------

# Controlled photo-tag vocabulary, seeded from what the 2026 album actually
# contains (see the photo-attribution handoff). Free-text tags are still
# accepted — this list is what the UI offers as checkboxes, not a whitelist.
PHOTO_TAG_VOCABULARY = [
    {"tag": "seed-starting", "description": "Trays, cups, grow lights, seedlings"},
    {"tag": "flower", "description": "Flowers, buds, husks (no variety recoverable)"},
    {"tag": "plan", "description": "Hand-drawn layouts, sketches, graph paper"},
    {"tag": "harvest", "description": "Harvest spreads, plates, curing crops"},
    {"tag": "wide-shot", "description": "Full-garden / yard overviews"},
    {"tag": "soil-prep", "description": "Mulch, cracked ground, bed building, fill"},
    {"tag": "pest-disease", "description": "Bugs, mildew, leaf damage, sunscald"},
    {"tag": "supplies", "description": "Soil bags, bins, pots, pallets, setups"},
    {"tag": "structure", "description": "Trellises, cages, greenhouse, raised beds"},
    {"tag": "unidentified", "description": "Nothing recoverable"},
]

MAX_TAGS_PER_PHOTO = 20
MAX_TAG_LENGTH = 60


def _normalize_tags(tags: Optional[List[str]]) -> str:
    """A tags array -> the comma-separated string stored on AlbumImage.

    Lowercased, trimmed, de-duplicated (order preserved), capped — so the
    ``?tag=`` filter can match whole tokens instead of substrings.
    ``None``/empty clears the tags.
    """
    if not tags:
        return ""
    seen, out = set(), []
    for raw in tags:
        tag = (raw or "").strip().lower()
        if not tag or tag in seen or len(tag) > MAX_TAG_LENGTH:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= MAX_TAGS_PER_PHOTO:
            break
    return ", ".join(out)[:500]


def _tag_filter(stmt, tag: str):
    """Restrict a statement to photos carrying one whole tag token.

    Token-exact (``flower`` must not match ``flowers``) and case-insensitive,
    implemented as LIKE patterns so it composes with the query's LIMIT/OFFSET.
    """
    token = tag.strip().lower()
    if not token:
        return stmt
    escaped = (
        token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    col = func.lower(AlbumImage.tags)
    return stmt.where(
        (col == token)
        | col.like(f"{escaped}, %", escape="\\")
        | col.like(f"%, {escaped}, %", escape="\\")
        | col.like(f"%, {escaped}", escape="\\")
    )


def _image_read(
    img: AlbumImage,
    variety: Optional[str],
    packet_variety: Optional[str],
    container_name: Optional[str] = None,
) -> AlbumImageRead:
    read = AlbumImageRead.model_validate(img)
    read.plant_variety = variety
    read.packet_variety = packet_variety
    read.container_name = container_name
    return read


def _image_read_full(session: Session, img: AlbumImage) -> AlbumImageRead:
    """Build an AlbumImageRead with all link names filled in."""
    plant = session.get(Plant, img.plant_id) if img.plant_id else None
    packet = session.get(SeedPacket, img.seed_packet_id) if img.seed_packet_id else None
    container = session.get(Container, img.container_id) if img.container_id else None
    return _image_read(
        img,
        plant.variety_name if plant else None,
        packet.variety_name if packet else None,
        container.name if container else None,
    )


@router.get("/api/album-images/vocabulary")
def photo_tag_vocabulary() -> dict:
    """The seeded photo-tag vocabulary (descriptions included for UI tooltips)."""
    return {"tags": PHOTO_TAG_VOCABULARY}


@router.get("/api/album-images/", response_model=List[AlbumImageRead])
def list_album_images(
    album_id: Optional[int] = None,
    plant_id: Optional[int] = None,
    seed_packet_id: Optional[int] = None,
    container_id: Optional[int] = None,
    tag: Optional[str] = None,
    unassigned_only: bool = False,
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> List[AlbumImageRead]:
    """List album photos, oldest-taken first, with their plant/packet/container assignment.

    Filters: ``album_id``, ``plant_id`` (photos of one plant),
    ``seed_packet_id`` (photos of one seed packet), ``container_id``
    (photos of one container), ``tag`` (photos carrying one tag token), or
    ``unassigned_only`` for the matching workflow (neither a plant nor a
    packet assigned — tags alone do not count as assigned). The matching
    workflow skips AI-generated images: they are not garden records.
    """
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    stmt = (
        select(AlbumImage, Plant.variety_name, SeedPacket.variety_name, Container.name)
        .outerjoin(Plant, Plant.id == AlbumImage.plant_id)
        .outerjoin(SeedPacket, SeedPacket.id == AlbumImage.seed_packet_id)
        .outerjoin(Container, Container.id == AlbumImage.container_id)
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
    if seed_packet_id is not None:
        stmt = stmt.where(AlbumImage.seed_packet_id == seed_packet_id)
    if container_id is not None:
        stmt = stmt.where(AlbumImage.container_id == container_id)
    if tag is not None:
        stmt = _tag_filter(stmt, tag)
    if unassigned_only:
        stmt = stmt.where(AlbumImage.plant_id.is_(None), AlbumImage.seed_packet_id.is_(None))
        # Triage matching skips AI-generated images: not garden records.
        stmt = stmt.where(AlbumImage.is_generated.is_(False))
    rows = session.exec(stmt).all()
    return [
        _image_read(img, variety, pkt_variety, container_name)
        for img, variety, pkt_variety, container_name in rows
    ]


def _apply_target_fields(session: Session, img: AlbumImage, body, provided: set) -> None:
    """Apply plant/packet/container/tags/notes from an assign request.

    Only fields explicitly present in the request are touched — this is what
    makes tags independent of the plant link: a tag-only PATCH or bulk-assign
    must never wipe a plant assignment. Plant and packet stay mutually
    exclusive with each other (both explicitly null unassigns, as before).
    """
    if "plant_id" in provided or "seed_packet_id" in provided:
        if body.seed_packet_id is not None:
            packet = session.get(SeedPacket, body.seed_packet_id)
            if packet is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Seed packet not found")
            img.seed_packet_id = body.seed_packet_id
            img.plant_id = None
        elif body.plant_id is not None:
            plant = session.get(Plant, body.plant_id)
            if plant is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plant not found")
            img.plant_id = body.plant_id
            img.seed_packet_id = None
        else:
            img.plant_id = None
            img.seed_packet_id = None
    if "container_id" in provided:
        if body.container_id is None:
            img.container_id = None
        else:
            container = session.get(Container, body.container_id)
            if container is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Container not found")
            img.container_id = body.container_id
    if "tags" in provided:
        img.tags = _normalize_tags(body.tags)
    if "notes" in provided:
        img.notes = (body.notes or "")[:2000]


@router.patch("/api/album-images/{image_id}", response_model=AlbumImageRead)
def assign_album_image(
    image_id: int,
    body: ImageAssignRequest,
    session: Session = Depends(get_session),
) -> AlbumImageRead:
    """Assign a photo to a plant, a seed packet, and/or a container, and/or
    set its tags and notes. Only fields present in the request change."""
    img = session.get(AlbumImage, image_id)
    if img is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Photo not found")
    _apply_target_fields(session, img, body, body.model_fields_set)
    session.add(img)
    session.commit()
    session.refresh(img)
    return _image_read_full(session, img)


@router.post("/api/album-images/bulk-assign")
def bulk_assign_album_images(
    body: ImageBulkAssignRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Assign many photos at once. Tags, notes and container links are
    independent of the plant/packet link — a tag-only call leaves existing
    plant assignments exactly as they were."""
    provided = body.model_fields_set
    if body.seed_packet_id is not None and session.get(SeedPacket, body.seed_packet_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Seed packet not found")
    if body.plant_id is not None and session.get(Plant, body.plant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plant not found")
    if body.container_id is not None and session.get(Container, body.container_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Container not found")
    ids = list(dict.fromkeys(body.image_ids))
    images = session.exec(select(AlbumImage).where(AlbumImage.id.in_(ids))).all()
    for img in images:
        _apply_target_fields(session, img, body, provided)
        session.add(img)
    session.commit()
    return {"updated": len(images)}
