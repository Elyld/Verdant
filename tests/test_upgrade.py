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
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

TMP = tempfile.mkdtemp(prefix="verdant-upgrade-")
os.environ.setdefault("GARDEN_DATA_DIR", os.path.join(TMP, "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", os.path.join(TMP, "uploads"))
os.environ.setdefault("IMMICH_BASE_URL", "http://immich.test")
os.environ.setdefault("IMMICH_API_KEY", "fake-key")

from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app import immich  # noqa: E402
from app.database import _apply_column_migrations  # noqa: E402
from app.routers.import_csv import _Ctx, _build_fertilization  # noqa: E402
from app.schemas import (  # noqa: E402
    AlbumImageRead,
    AlbumRead,
    FertilizationRead,
    ObservationRead,
)
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


def test_album_null_exif_and_source_url_serialize_cleanly():
    """PR #12 added nullable EXIF/source_url columns; rows created before it
    (or never synced) hold NULLs. /api/albums must not 500 on them."""
    img = AlbumImageRead.model_validate(
        SimpleNamespace(
            id=1, file_path="/uploads/albums/1/a.jpg", title="A",
            original_name="a.jpg", source_url=None,
            imported_at=datetime(2026, 9, 25, 12, 0, 0),
            taken_at=None, camera_make=None, camera_model=None,
            latitude=None, longitude=None,
        )
    )
    assert (img.source_url, img.camera_make, img.camera_model) == ("", "", "")
    album = AlbumRead.model_validate(
        SimpleNamespace(
            id=1, name="Old", created_at=datetime(2026, 9, 25, 12, 0, 0),
            source_url=None, images=[img],
        )
    )
    assert album.source_url == ""


def test_fertilization_import_empty_amount_on_legacy_db(tmp_path):
    """Databases created by the initial release still carry NOT NULL on
    fertilization_logs.amount_used. Importing a row with no amount must not
    500 (reported 2026-09-25)."""
    db = str(tmp_path / "garden.db")
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        # Recreate the table the way the initial release built it: amount_used NOT NULL.
        conn.exec_driver_sql("DROP TABLE fertilization_logs")
        conn.exec_driver_sql(
            "CREATE TABLE fertilization_logs (id INTEGER PRIMARY KEY, date TEXT,"
            " fertilizer_name TEXT NOT NULL, fertilizer_id INTEGER,"
            " npk_ratio TEXT NOT NULL, amount_used TEXT NOT NULL,"
            " amount_value REAL, amount_unit TEXT,"
            " plant_id INTEGER, location_id INTEGER, notes TEXT NOT NULL)"
        )
        conn.commit()
    with Session(engine) as session:
        ctx = _Ctx(session)
        row = {
            "Log ID": "FE-LEG-001", "Link to Plant": "", "Fertilizer": "",
            "Date": "08/09/2026", "Amount / Concentration": "",
            "Application": "Liquid", "Notes": "",
        }
        res = _build_fertilization(row, ctx)
        assert res["status"] == "new", res
        session.add(res["make"]())
        session.commit()  # IntegrityError before the fix
    con = sqlite3.connect(db)
    try:
        val = con.execute("SELECT amount_used FROM fertilization_logs").fetchone()[0]
    finally:
        con.close()
    assert val == ""


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


JPEG = bytes.fromhex("ffd8ffe000104a4649460001010000010001000000") + b"\x00" * 64


def _stub_immich(monkeypatch):
    """Stub the Immich client: 4 photos + 1 video in album 'big'."""
    import app.routers.immich as immich_router

    monkeypatch.setattr(
        immich_router.immich, "get_album",
        lambda _id: {"id": "big", "albumName": "Batch Garden", "assetCount": 5},
    )
    monkeypatch.setattr(
        immich_router.immich, "list_album_assets",
        lambda _id: [
            {"id": f"p{i}", "type": "IMAGE", "originalFileName": f"pic{i}.jpg"}
            for i in range(4)
        ] + [{"id": "v9", "type": "VIDEO", "originalFileName": "clip.mp4"}],
    )
    monkeypatch.setattr(
        immich_router.immich, "download_asset", lambda _id: JPEG
    )


def test_immich_import_batches_and_is_idempotent(monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import init_db
    from app.main import app

    _stub_immich(monkeypatch)
    init_db()
    with TestClient(app) as client:
        # batch 1 of 2
        r1 = client.post("/api/immich/albums/big/import?offset=0&limit=2")
        assert r1.status_code == 200, r1.text[:200]
        b1 = r1.json()
        assert (b1["total"], b1["created"], b1["done"]) == (4, 2, False)
        assert b1["imported"] == 2

        # retrying batch 1 adds nothing (no dupes)
        r1b = client.post(
            f"/api/immich/albums/big/import?offset=0&limit=2&album_id={b1['album_id']}"
        )
        assert r1b.json()["created"] == 0
        assert r1b.json()["imported"] == 2

        # batch 2 finishes (video skipped)
        r2 = client.post(
            f"/api/immich/albums/big/import?offset=2&limit=2&album_id={b1['album_id']}"
        )
        b2 = r2.json()
        assert (b2["created"], b2["done"], b2["imported"]) == (2, True, 4)
        assert b2["album_name"] == "Batch Garden"

        # offset without album_id is rejected
        bad = client.post("/api/immich/albums/big/import?offset=2&limit=2")
        assert bad.status_code == 400


def _denied_transport():
    """Mock Immich server that 403s every original download (missing asset.download)."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/original"):
            return httpx.Response(403, json={"message": "forbidden"})
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def test_download_asset_403_mentions_permission(monkeypatch):
    transport = _denied_transport()

    def fake_client():
        base, key = immich._config()
        return httpx.Client(
            base_url=base, headers={"x-api-key": key}, transport=transport
        )

    monkeypatch.setattr(immich, "_client", fake_client)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        immich.download_asset("abc123")
    assert "asset.download" in exc_info.value.detail


def test_immich_import_reports_download_failures(monkeypatch, caplog):
    """When every download is denied, the batch reports failures instead of a
    silent 'imported 0'."""
    import logging

    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    import app.routers.immich as immich_router
    from app.database import init_db
    from app.main import app

    def denied(_id: str):
        raise HTTPException(
            status_code=502,
            detail="Immich refused the download (403). The API key needs the "
            "'asset.download' permission.",
        )

    monkeypatch.setattr(
        immich_router.immich,
        "get_album",
        lambda _id: {"id": "locked", "albumName": "Locked", "assetCount": 2},
    )
    monkeypatch.setattr(
        immich_router.immich,
        "list_album_assets",
        lambda _id: [
            {"id": "p1", "type": "IMAGE", "originalFileName": "a.jpg"},
            {"id": "p2", "type": "IMAGE", "originalFileName": "b.jpg"},
        ],
    )
    monkeypatch.setattr(immich_router.immich, "download_asset", denied)

    init_db()
    with caplog.at_level(logging.WARNING, logger="verdant.immich"):
        with TestClient(app) as client:
            r = client.post("/api/immich/albums/locked/import?offset=0&limit=50")
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["created"] == 0
    assert body["failed"] == 2
    assert body["imported"] == 0
    assert any("asset.download" in e for e in body["errors"])
    # failures are logged server-side for `docker logs`
    assert "2 failed" in caplog.text


def test_migration_relaxes_stale_not_null_constraints(tmp_path):
    """The initial release built fertilization_logs with NOT NULL string
    columns; the model later made them optional. The migration must relax
    those stale constraints (table rebuild) so NULL inserts stop 500ing —
    and leave constraints the model still wants (fertilizer_name) alone."""
    db = str(tmp_path / "garden.db")
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("DROP TABLE fertilization_logs")
        conn.exec_driver_sql(
            "CREATE TABLE fertilization_logs (id INTEGER PRIMARY KEY, date TEXT,"
            " fertilizer_name TEXT NOT NULL, fertilizer_id INTEGER,"
            " npk_ratio TEXT NOT NULL, amount_used TEXT NOT NULL,"
            " plant_id INTEGER, location_id INTEGER, notes TEXT NOT NULL)"
        )
        conn.exec_driver_sql(
            "INSERT INTO fertilization_logs (date, fertilizer_name, npk_ratio,"
            " amount_used, notes) VALUES ('2026-01-05', 'Old Faithful',"
            " '10-10-10', '1 tbsp', 'legacy row')"
        )
        conn.commit()
    _apply_column_migrations(engine)
    con = sqlite3.connect(db)
    try:
        flags = {
            r[1]: r[3] for r in con.execute("PRAGMA table_info(fertilization_logs)")
        }
        # relaxed: model says nullable
        assert flags["amount_used"] == 0
        assert flags["npk_ratio"] == 0
        assert flags["notes"] == 0
        # untouched: model still requires these
        assert flags["fertilizer_name"] == 1
        assert flags["date"] == 1
        # legacy data survived the rebuild
        assert con.execute(
            "SELECT fertilizer_name, amount_used FROM fertilization_logs"
        ).fetchone() == ("Old Faithful", "1 tbsp")
        # NULL inserts now work at the SQL level (no model coercion involved)
        con.execute(
            "INSERT INTO fertilization_logs (date, fertilizer_name)"
            " VALUES ('2026-02-01', 'X')"
        )
        con.commit()
        assert con.execute(
            "SELECT amount_used FROM fertilization_logs WHERE date = '2026-02-01'"
        ).fetchone() == (None,)
    finally:
        con.close()
