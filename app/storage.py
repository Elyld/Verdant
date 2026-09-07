"""Secure image storage helpers for uploaded files."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Iterable, List

from fastapi import HTTPException, UploadFile, status

from app.database import UPLOAD_DIR

MAX_BYTES = 8 * 1024 * 1024  # 8 MB per image
CHUNK = 64 * 1024

# canonical extension per sniffed content type (never trust client filename)
ALLOWED_TYPES = {
    "jpeg": ".jpg",
    "png": ".png",
    "gif": ".gif",
    "webp": ".webp",
    "bmp": ".bmp",
}


def _sniff(head: bytes) -> str | None:
    """Identify an image by magic bytes (stdlib imghdr is gone in 3.13)."""
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:2] == b"BM":
        return "bmp"
    return None


async def save_upload(file: UploadFile, subdir: str) -> str:
    """Stream one upload to disk. Returns the public URL path (/uploads/...).

    Filenames are randomly generated, so a hostile client filename cannot
    traverse directories or overwrite existing files.
    """
    target_dir = UPLOAD_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    head = await file.read(32)
    kind = _sniff(head)
    if kind not in ALLOWED_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type for '{file.filename}' (jpg/png/gif/webp/bmp only).",
        )

    name = f"{secrets.token_hex(16)}{ALLOWED_TYPES[kind]}"
    path = target_dir / name
    written = 0
    try:
        with path.open("wb") as out:
            out.write(head)
            written += len(head)
            while chunk := await file.read(CHUNK):
                written += len(chunk)
                if written > MAX_BYTES:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"'{file.filename}' exceeds the {MAX_BYTES // (1024 * 1024)}MB limit.",
                    )
                out.write(chunk)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return f"/uploads/{subdir}/{name}"


async def save_uploads(files: Iterable[UploadFile] | None, subdir: str) -> List[str]:
    saved: List[str] = []
    for file in files or []:
        if not file or not file.filename:
            continue
        try:
            saved.append(await save_upload(file, subdir))
        except Exception:
            for url in saved:
                delete_stored(url)
            raise
    return saved


def delete_stored(url_path: str) -> None:
    """Delete a file previously returned by save_upload; ignore anything else."""
    prefix = "/uploads/"
    if not url_path.startswith(prefix):
        return
    candidate = (UPLOAD_DIR / url_path[len(prefix) :]).resolve()
    root = UPLOAD_DIR.resolve()
    if root == candidate or root not in candidate.parents:
        return
    try:
        Path(candidate).unlink(missing_ok=True)
    except OSError:
        pass
