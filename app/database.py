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


# Columns added after the initial release. create_all() won't add them to
# existing databases, so we ALTER TABLE them in when missing (SQLite only).
_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("plants", "water_every_days", "INTEGER"),
    ("plants", "feed_every_days", "INTEGER"),
    ("observation_logs", "temp_c", "FLOAT"),
    ("observation_logs", "weather_summary", "TEXT"),
    ("watering_logs", "plant_id", "INTEGER"),
]


def _apply_column_migrations() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        for table, column, coltype in _COLUMN_MIGRATIONS:
            existing = {
                row[1]
                for row in conn.exec_driver_sql(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }
            if column not in existing:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"
                )


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
