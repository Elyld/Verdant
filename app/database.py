"""SQLite engine/session wiring for the garden log app."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("GARDEN_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = Path(os.getenv("GARDEN_UPLOAD_DIR", BASE_DIR / "uploads"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("GARDEN_DATABASE_URL", f"sqlite:///{DATA_DIR / 'garden.db'}")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


def init_db() -> None:
    """Create tables and enable WAL for better concurrent reads."""
    import app.models  # noqa: F401  (ensure models are registered)

    SQLModel.metadata.create_all(engine)
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
