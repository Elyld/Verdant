"""Regression tests: upgrading an old database in place, and Immich v3 albums.

- An existing garden.db from an older release must gain new columns on
  startup (the migration syncs model columns automatically), not 500.
- Rows with NULL string fields must serialize cleanly (None -> "").
- Immich v3 removed the embedded ``assets`` array from GET /api/albums/{id};
  album contents must come from POST /api/search/metadata (paginated).
"""
import json
import os
import sqlite3
import tempfile
from types import SimpleNamespace

import httpx
import pytest

TMP = tempfile.mkdtemp(prefix="verdant-upgrade-")
os.environ.setdefault("GARDEN_DATA_DIR", os.path.join(TMP, "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", os.path.join(TMP, "uploads"))
os.environ.setdefault("IMMICH_BASE_URL", "http://immich.test")
os.environ.setdefault("IMMICH_API_KEY", "fake-key")

from sqlmodel import create_engine  # noqa: E402

from app import immich  # noqa: E402
from app.database import _apply_column_migrations  # noqa: E402
from app.schemas import FertilizationRead, ObservationRead  # noqa: E402
import app.models  # noqa: E402,F401


def _old_database(path: str) -> None:
    """Write a database shaped like a pre-garden-core release: tables exist
    but lack the newer columns, and string fields hold NULLs."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE fertilization_logs (id INTEGER PRIMARY KEY, date TEXT,"
        " fertilizer_name TEXT, npk_ratio TEXT, amount_used TEXT, notes TEXT)"
    )
    con.execute(
        "INSERT INTO fertilization_logs (date, fertilizer_name, npk_ratio,"
        " amount_used, notes) VALUES ('2026-01-05', 'Old Faithful', NULL, NULL, NULL)"
    )
    con.execute(
        "CREATE TABLE observation_logs (id INTEGER PRIMARY KEY, date TEXT,"
        " plant_name TEXT, health_scale INTEGER, watering_status INTEGER,"
        " pest_sightings TEXT, notes TEXT)"
    )
    con.execute(
        "INSERT INTO observation_logs (date, plant_name, health_scale,"
        " watering_status, notes) VALUES ('2026-01-06', 'Tomato', 8, 1, NULL)"
    )
    con.commit()
    con.close()


def test_migration_adds_missing_columns(tmp_path):
    db = str(tmp_path / "garden.db")
    _old_database(db)
    _apply_column_migrations(create_engine(f"sqlite:///{db}"))
    con = sqlite3.connect(db)
    try:
        fert_cols = {r[1] for r in con.execute("PRAGMA table_info(fertilization_logs)")}
        obs_cols = {r[1] for r in con.execute("PRAGMA table_info(observation_logs)")}
    finally:
        con.close()
    assert "fertilizer_id" in fert_cols
    assert "plant_id" in obs_cols
    assert "temp_c" in obs_cols
    # old data untouched
    con = sqlite3.connect(db)
    try:
        assert con.execute(
            "SELECT fertilizer_name FROM fertilization_logs"
        ).fetchone() == ("Old Faithful",)
    finally:
        con.close()


def test_null_string_fields_serialize_cleanly():
    fert = FertilizationRead.model_validate(
        SimpleNamespace(
            id=1, date="2026-01-05", fertilizer_name="Old Faithful",
            npk_ratio=None, amount_used=None, notes=None,
            fertilizer_id=None, plant_id=None, location_id=None,
        )
    )
    assert (fert.npk_ratio, fert.amount_used, fert.notes) == ("", "", "")
    obs = ObservationRead.model_validate(
        SimpleNamespace(
            id=1, date="2026-01-06", plant_name="Tomato", health_scale=8,
            watering_status=True, pest_sightings=None, notes=None,
            images=[], plant_id=None, temp_c=None, weather_summary=None,
        )
    )
    assert obs.notes == ""


def _v3_transport():
    """Mock an Immich v3 server: album detail has no assets array."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/albums/abc":
            return httpx.Response(
                200,
                json={"id": "abc", "albumName": "Garden", "assetCount": 3},
            )
        if req.url.path == "/api/search/metadata":
            body = json.loads(req.content)
            assert body["albumIds"] == ["abc"]
            if body["page"] == 1:
                items = [
                    {"id": "a1", "type": "IMAGE", "originalFileName": "one.jpg"},
                    {"id": "a2", "type": "IMAGE", "originalFileName": "two.jpg"},
                ]
                return httpx.Response(
                    200,
                    json={"assets": {"items": items, "nextPage": "2",
                                    "total": 3, "count": 2}},
                )
            return httpx.Response(
                200,
                json={"assets": {"items": [
                    {"id": "a3", "type": "IMAGE", "originalFileName": "three.jpg"},
                ], "nextPage": None, "total": 3, "count": 1}},
            )
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def test_list_album_assets_uses_search_and_paginates(monkeypatch):
    transport = _v3_transport()

    def fake_client():
        base, key = immich._config()
        return httpx.Client(
            base_url=base, headers={"x-api-key": key}, transport=transport
        )

    monkeypatch.setattr(immich, "_client", fake_client)
    assets = immich.list_album_assets("abc")
    assert [a["id"] for a in assets] == ["a1", "a2", "a3"]
