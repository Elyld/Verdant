"""Backup & restore: the whole database plus uploaded files as one zip download.

Export:  GET  /api/backup/export  -> verdant-backup-<timestamp>.zip
         { data.json: every table's rows, files/: the uploaded images }

Import:  POST /api/backup/import  (multipart "file")
         Wipes current data, restores rows (ids preserved so links stay
         intact) and re-extracts the uploaded files. Reports per-table counts.
"""
from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime, timezone
from typing import List, Type

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import Session, SQLModel, delete, select

from app.database import UPLOAD_DIR, get_session
import app.models as models_module
from app.version import __version__

router = APIRouter(prefix="/api/backup", tags=["backup"])

FORMAT_VERSION = 1
FORMAT_MARKER = "verdant-backup"


def _discover_models() -> List[Type[SQLModel]]:
    """Every table model, parents before children (insert order).

    Derived from SQLModel's metadata so a new model is backed up
    automatically — there is no hand-maintained list to forget.
    """
    by_table = {}
    for name in dir(models_module):
        obj = getattr(models_module, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, SQLModel)
            and getattr(obj, "__tablename__", None) in SQLModel.metadata.tables
        ):
            by_table[obj.__table__] = obj
    return [by_table[t] for t in SQLModel.metadata.sorted_tables if t in by_table]


# Parents before children (insert order); reversed for wipe order.
TABLES_IN_ORDER: List[Type[SQLModel]] = _discover_models()

# Image tables carry uploaded files (detected by the file_path column).
IMAGE_TABLES = {m for m in TABLES_IN_ORDER if "file_path" in m.__table__.columns}


def _upload_relpath(file_path: str) -> str | None:
    """Turn a stored file_path like '/uploads/posts/3/a.jpg' into a path
    relative to UPLOAD_DIR. Returns None for remote URLs / unknown schemes."""
    if not file_path or not file_path.startswith("/uploads/"):
        return None
    return file_path[len("/uploads/"):]


@router.get("/export")
def export_backup(session: Session = Depends(get_session)):
    """Download a zip containing data.json (all tables) + files/ (uploads)."""
    buf = io.BytesIO()
    tables: dict[str, list] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for model in TABLES_IN_ORDER:
            rows = session.exec(select(model).order_by(model.id)).all()
            dumped = [r.model_dump(mode="json") for r in rows]
            tables[model.__tablename__] = dumped
            if model in IMAGE_TABLES:
                for d in dumped:
                    rel = _upload_relpath(d.get("file_path") or "")
                    if not rel:
                        continue
                    src = UPLOAD_DIR / rel
                    if src.is_file():
                        zf.write(src, f"files/{rel}")
        manifest = {
            "format": FORMAT_MARKER,
            "format_version": FORMAT_VERSION,
            "app_version": __version__,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tables": tables,
        }
        zf.writestr("data.json", json.dumps(manifest, indent=1))
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="verdant-backup-{stamp}.zip"'},
    )


@router.post("/import")
def import_backup(
    file: UploadFile = File(..., description="A zip previously downloaded from /api/backup/export"),
    session: Session = Depends(get_session),
):
    """Restore from a backup zip. REPLACES all current data and uploads."""
    try:
        raw = file.file.read()
        zf = zipfile.ZipFile(io.BytesIO(raw))
        manifest = json.loads(zf.read("data.json"))
    except Exception:
        raise HTTPException(status_code=400, detail="Not a readable Verdant backup zip.")
    if manifest.get("format") != FORMAT_MARKER:
        raise HTTPException(status_code=400, detail="Not a Verdant backup file.")

    tables = manifest.get("tables", {})
    try:
        # Wipe children first.
        for model in reversed(TABLES_IN_ORDER):
            session.exec(delete(model))
        # Clear the upload dir (it is fully app-managed).
        if UPLOAD_DIR.exists():
            for child in UPLOAD_DIR.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        # Restore uploaded files (zip-slip guarded).
        base = UPLOAD_DIR.resolve()
        for name in zf.namelist():
            if not name.startswith("files/") or name.endswith("/"):
                continue
            target = (base / name[len("files/"):]).resolve()
            if base not in target.parents and target != base:
                raise HTTPException(status_code=400, detail="Unsafe path in backup zip.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
        # Insert parents first; ids are preserved so foreign keys line up.
        # model_validate (not __init__) coerces ISO date strings back to dates.
        counts: dict[str, int] = {}
        for model in TABLES_IN_ORDER:
            rows = tables.get(model.__tablename__, [])
            for rd in rows:
                session.add(model.model_validate(rd))
            counts[model.__tablename__] = len(rows)
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"Restore failed: {exc}")
    return {"restored": counts, "format_version": manifest.get("format_version")}
