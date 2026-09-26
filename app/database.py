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
    _relax_not_null_constraints(target_engine, present)
    _backfill_packet_vendor_names(target_engine)


def _backfill_packet_vendor_names(target_engine) -> None:
    """One-time backfill: packets created while the vendor was a link into
    seed_sources get the vendor's name copied onto vendor_name, so the packet
    stands alone (the vendor dropdown no longer lists one row per variety)."""
    with target_engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "seed_packets" not in tables or "seed_sources" not in tables:
            return
        cols = {
            row[1] for row in conn.exec_driver_sql('PRAGMA table_info("seed_packets")').fetchall()
        }
        if "vendor_name" not in cols or "vendor_id" not in cols:
            return
        conn.exec_driver_sql(
            "UPDATE seed_packets SET vendor_name = "
            "(SELECT source FROM seed_sources WHERE seed_sources.id = seed_packets.vendor_id) "
            "WHERE (vendor_name IS NULL OR vendor_name = '') AND vendor_id IS NOT NULL"
        )
        conn.commit()


def _relax_not_null_constraints(target_engine, present: set[str]) -> None:
    """Drop stale NOT NULL constraints left by older releases (SQLite only).

    The model is the source of truth and every Verdant data column is
    nullable; very old databases still carry NOT NULL from the first
    releases, which 500s inserts that legitimately leave the field empty
    (e.g. fertilization_logs.amount_used). SQLite cannot ALTER a column, so
    an affected table is rebuilt: new table from the model schema, data
    copied over, old table dropped, indexes re-created. Only ever relaxes —
    constraints are never tightened.

    Runs on its own AUTOCOMMIT connection: PRAGMA foreign_keys is a no-op
    inside a transaction, and the rebuild must disable enforcement while it
    swaps the tables.
    """
    from sqlalchemy import MetaData
    from sqlalchemy.schema import CreateTable

    with target_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in present:
                continue
            disk = {
                row[1]: row[3]  # name -> notnull flag
                for row in conn.exec_driver_sql(
                    f'PRAGMA table_info("{table.name}")'
                ).fetchall()
            }
            stale = [
                column.name
                for column in table.columns
                if column.nullable and disk.get(column.name) == 1
            ]
            if not stale:
                continue
            tmp_name = f"__verdant_rebuild_{table.name}"
            # Copy every table so foreign keys resolve when compiling the DDL.
            tmp_meta = MetaData()
            for other in SQLModel.metadata.sorted_tables:
                other.to_metadata(
                    tmp_meta, name=tmp_name if other.name == table.name else None
                )
            ddl = str(
                CreateTable(tmp_meta.tables[tmp_name]).compile(
                    dialect=target_engine.dialect
                )
            )
            indexes = [
                row[1]
                for row in conn.exec_driver_sql(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
                    (table.name,),
                ).fetchall()
            ]
            common = [c for c in table.columns.keys() if c in disk]
            cols_csv = ", ".join(f'"{c}"' for c in common)
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            try:
                conn.exec_driver_sql(ddl)
                conn.exec_driver_sql(
                    f'INSERT INTO "{tmp_name}" ({cols_csv}) '
                    f'SELECT {cols_csv} FROM "{table.name}"'
                )
                conn.exec_driver_sql(f'DROP TABLE "{table.name}"')
                conn.exec_driver_sql(
                    f'ALTER TABLE "{tmp_name}" RENAME TO "{table.name}"'
                )
                for index_sql in indexes:
                    conn.exec_driver_sql(index_sql)
            except Exception:
                conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{tmp_name}"')
                raise
            finally:
                conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
