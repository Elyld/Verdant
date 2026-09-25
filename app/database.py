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
    _apply_column_migrations()
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")


# init_db() also brings old databases up to date: create_all() creates missing
# tables but never adds columns to tables that already exist, so upgrading
# from an older release would 500 on the new fields. Instead of a
# hand-maintained list (which inevitably misses some), we sync automatically:
# for every mapped table, ADD COLUMN for each model column absent on disk.
# All Verdant columns are nullable, so ADD COLUMN is always safe (SQLite).


def _apply_column_migrations(target_engine=None) -> None:
    """Add any model columns missing from existing tables (SQLite only).

    ``target_engine`` defaults to the app engine; tests pass their own engine
    pointed at a scratch database shaped like an old release.
    """
    target_engine = target_engine or engine
    url = str(target_engine.url)
    if not url.startswith("sqlite"):
        return
    with target_engine.connect() as conn:
        present = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in present:
                continue  # create_all() already made it with the full schema
            existing = {
                row[1]
                for row in conn.exec_driver_sql(
                    f'PRAGMA table_info("{table.name}")'
                ).fetchall()
            }
            for column in table.columns:
                if column.name not in existing:
                    coltype = column.type.compile(dialect=target_engine.dialect)
                    conn.exec_driver_sql(
                        f'ALTER TABLE "{table.name}" '
                        f'ADD COLUMN "{column.name}" {coltype}'
                    )


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
