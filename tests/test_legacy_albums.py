"""Defect report 3 (2026-10-28): legacy albums, duplicate detection,
season modelling, plus the generated-image flag.

Shares the same temp DB as the other test modules; every test cleans up
the rows it creates so nothing leaks. Album/plant names are unique to
this file so a full-suite run can't collide with other modules.
"""
from __future__ import annotations

import os
import sqlite3
import struct
import tempfile
import zlib
from datetime import date as Date
from datetime import datetime
from pathlib import Path

import pytest  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="legacy-albums-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, delete, select  # noqa: E402

from app import yearbook as yearbook_mod  # noqa: E402
from app.database import UPLOAD_DIR, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Album, AlbumImage, Container, Plant, Planting  # noqa: E402
from app.photo_dates import is_generated_filename, parse_filename_date  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


CREATED = {"plants": [], "albums": [], "images": [], "containers": [], "plantings": []}


@pytest.fixture(autouse=True)
def clean_rows():
    for key in CREATED:
        CREATED[key].clear()
    yield
    with Session(engine) as s:
        if CREATED["images"]:
            s.exec(delete(AlbumImage).where(AlbumImage.id.in_(CREATED["images"])))
        if CREATED["plantings"]:
            s.exec(delete(Planting).where(Planting.id.in_(CREATED["plantings"])))
        if CREATED["albums"]:
            s.exec(delete(Album).where(Album.id.in_(CREATED["albums"])))
        if CREATED["plants"]:
            s.exec(delete(Plant).where(Plant.id.in_(CREATED["plants"])))
        if CREATED["containers"]:
            s.exec(delete(Container).where(Container.id.in_(CREATED["containers"])))
        s.commit()


def _png_bytes(width: int = 4, height: int = 4) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x7f\x9c\x6a" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _make_album(session, name, source_url="") -> int:
    album = Album(name=name, source_url=source_url)
    session.add(album)
    session.commit()
    session.refresh(album)
    CREATED["albums"].append(album.id)
    return album.id


def _make_image(session, album_id, file_bytes=b"fake-bytes", fname="a.jpg",
                original_name="", taken_at=None, is_generated=False,
                source_url="") -> int:
    target = UPLOAD_DIR / f"albums/{album_id}"
    target.mkdir(parents=True, exist_ok=True)
    (target / fname).write_bytes(file_bytes)
    img = AlbumImage(
        album_id=album_id,
        file_path=f"/uploads/albums/{album_id}/{fname}",
        title=original_name or fname,
        original_name=original_name or fname,
        source_url=source_url,
        taken_at=taken_at,
        is_generated=is_generated,
    )
    session.add(img)
    session.commit()
    session.refresh(img)
    CREATED["images"].append(img.id)
    return img.id


def _make_plant(session, name, **kwargs) -> int:
    plant = Plant(variety_name=name, species_type="Pepper", **kwargs)
    session.add(plant)
    session.commit()
    session.refresh(plant)
    CREATED["plants"].append(plant.id)
    return plant.id


# --------------------------------------------------------------------------- #
# Filename dates + generated flag (pure)
# --------------------------------------------------------------------------- #
def test_parse_filename_date():
    assert parse_filename_date("20250602_195615.jpg") == datetime(2025, 6, 2, 19, 56, 15)
    assert parse_filename_date("file-abc123-20250602_195615.jpg") == datetime(2025, 6, 2, 19, 56, 15)
    assert parse_filename_date("image-1761951517029.jpg") == datetime(2025, 10, 31, 22, 58, 37, 29000)
    assert parse_filename_date("chatgpt-1759971053683.jpg") == datetime(2025, 10, 9, 0, 50, 53, 683000)
    assert parse_filename_date("20251340_999999.jpg") is None  # invalid month/day/time
    assert parse_filename_date("IMG_0001.jpg") is None
    assert parse_filename_date("image-123.jpg") is None  # too short for epoch ms
    assert parse_filename_date("image-0000000000000.jpg") is None  # epoch 0: bogus
    assert parse_filename_date("photo-9999999999999.jpg") is None  # year 2286: bogus


def test_is_generated_filename():
    assert is_generated_filename("chatgpt-1759971053683.jpg") is True
    assert is_generated_filename("chatgpt_foo.jpg") is True
    assert is_generated_filename("ChatGPT-foo.JPG") is True
    assert is_generated_filename("image-1761951517029.jpg") is False
    assert is_generated_filename("chatgpt.jpg") is False


# --------------------------------------------------------------------------- #
# Fix 1: source_url adoption
# --------------------------------------------------------------------------- #
def test_patch_album_source_url(client):
    with Session(engine) as s:
        album_id = _make_album(s, "LegacyPatch", "")

    resp = client.patch(f"/api/albums/{album_id}", json={"source_url": "immich:XYZ"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["source_url"] == "immich:XYZ"

    resp = client.patch(f"/api/albums/{album_id}", json={"source_url": "http://x"})
    assert resp.status_code == 422, resp.text

    resp = client.patch(f"/api/albums/{album_id}", json={"source_url": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["source_url"] == ""

    resp = client.patch(f"/api/albums/{album_id}", json={"name": "LegacyPatch2"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "LegacyPatch2"

    assert client.patch("/api/albums/999999", json={"name": "x"}).status_code == 404


def test_immich_import_stamps_source_url(client, monkeypatch):
    assets = [
        {"id": "b1", "type": "IMAGE", "originalFileName": "20250602_195615.jpg"},
        {"id": "b2", "type": "IMAGE", "originalFileName": "chatgpt-1759971053683.jpg"},
    ]
    monkeypatch.setattr("app.immich.get_album", lambda album_id: {"albumName": "LegacyImport"})
    monkeypatch.setattr("app.immich.list_album_assets", lambda album_id: assets)
    monkeypatch.setattr("app.immich.download_asset", lambda asset_id: _png_bytes())

    with Session(engine) as s:
        album_id = _make_album(s, "LegacyImport", "")

    resp = client.post("/api/immich/albums/ZZZ/import",
                       params={"offset": 0, "limit": 50, "album_id": album_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 2

    with Session(engine) as s:
        album = s.get(Album, album_id)
        assert album.source_url == "immich:ZZZ"
        imgs = sorted(album.images, key=lambda i: i.original_name)
        by_name = {i.original_name: i for i in imgs}
        # No asset date: filename date fills taken_at.
        assert by_name["20250602_195615.jpg"].taken_at == datetime(2025, 6, 2, 19, 56, 15)
        # chatgpt-* name is flagged generated.
        assert by_name["chatgpt-1759971053683.jpg"].is_generated is True


# --------------------------------------------------------------------------- #
# Fix 2: backfill-dates
# --------------------------------------------------------------------------- #
def test_backfill_dates_fills_blanks_only(client):
    with Session(engine) as s:
        album_id = _make_album(s, "LegacyBackfill", "")
        dated = _make_image(s, album_id, fname="d.jpg",
                            original_name="20250602_195615.jpg")
        gen = _make_image(s, album_id, fname="g.jpg",
                          original_name="chatgpt-9.jpg")
        kept = _make_image(s, album_id, fname="k.jpg",
                           original_name="20250101_000000.jpg",
                           taken_at=datetime(2024, 1, 1, 0, 0, 0))

    resp = client.post(f"/api/albums/{album_id}/backfill-dates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert body["updated"] == 2  # dated + generated flag; kept untouched

    with Session(engine) as s:
        assert s.get(AlbumImage, dated).taken_at == datetime(2025, 6, 2, 19, 56, 15)
        assert s.get(AlbumImage, gen).is_generated is True
        assert s.get(AlbumImage, gen).taken_at is None  # no date invented
        assert s.get(AlbumImage, kept).taken_at == datetime(2024, 1, 1, 0, 0, 0)

    assert client.post("/api/albums/999999/backfill-dates").status_code == 404


# --------------------------------------------------------------------------- #
# Fix 3: merge-duplicates over sourceless name groups
# --------------------------------------------------------------------------- #
def test_merge_removes_content_subset(client):
    with Session(engine) as s:
        keeper_id = _make_album(s, "LegacyDupe 2025", "")
        subset_id = _make_album(s, "LegacyDupe 2025", "")
        _make_image(s, keeper_id, file_bytes=b"photo-A", fname="a.jpg")
        _make_image(s, keeper_id, file_bytes=b"photo-B", fname="b.jpg")
        sub_file = UPLOAD_DIR / f"albums/{subset_id}" / "a-copy.jpg"
        _make_image(s, subset_id, file_bytes=b"photo-A", fname="a-copy.jpg")

    resp = client.post("/api/albums/merge-duplicates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["albums_removed"] == 1
    assert body["groups_merged"] == 1
    assert any("by file content" in line for line in body["detail"])
    assert not sub_file.exists()

    with Session(engine) as s:
        assert s.get(Album, subset_id) is None
        kept = s.get(Album, keeper_id)
        assert len(kept.images) == 2


def test_merge_name_group_overlap_left_alone(client):
    with Session(engine) as s:
        a_id = _make_album(s, "LegacyOverlap 2025", "")
        b_id = _make_album(s, "LegacyOverlap 2025", "")
        _make_image(s, a_id, file_bytes=b"photo-A", fname="a.jpg")
        _make_image(s, a_id, file_bytes=b"photo-B", fname="b.jpg")
        _make_image(s, b_id, file_bytes=b"photo-A", fname="a.jpg")
        _make_image(s, b_id, file_bytes=b"photo-C", fname="c.jpg")

    resp = client.post("/api/albums/merge-duplicates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["albums_removed"] == 0
    assert any("neither contains the other" in line for line in body["detail"])

    with Session(engine) as s:
        assert s.get(Album, a_id) is not None
        assert s.get(Album, b_id) is not None


def test_merge_noop_explains_itself(client):
    with Session(engine) as s:
        _make_album(s, "LegacySolo", "")
        _make_album(s, "LegacyOther", "immich:SOLO")

    resp = client.post("/api/albums/merge-duplicates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["groups_merged"] == 0
    assert body["albums_removed"] == 0
    assert any("No duplicates merged" in line for line in body["detail"])


# --------------------------------------------------------------------------- #
# Fix 4: season filter
# --------------------------------------------------------------------------- #
def test_season_year_filter(client):
    with Session(engine) as s:
        p1 = _make_plant(s, "LegacySeason A", date_planted=Date(2025, 5, 1))
        p2 = _make_plant(s, "LegacySeason B", date_planted=Date(2026, 3, 1),
                         season_year=2025)
        p3 = _make_plant(s, "LegacySeason C", date_planted=Date(2026, 4, 1))
        p4 = _make_plant(s, "LegacySeason D")
        container = Container(name="LegacySeason Bed", season_year=2025)
        s.add(container)
        s.commit()
        s.refresh(container)
        CREATED["containers"].append(container.id)
        planting = Planting(container_id=container.id, plant_id=p4,
                            season_year=2025, slot=0)
        s.add(planting)
        s.commit()
        s.refresh(planting)
        CREATED["plantings"].append(planting.id)
        p5 = _make_plant(s, "LegacySeason E")

    resp = client.get("/api/plants/", params={"season_year": 2025})
    assert resp.status_code == 200, resp.text
    got = {p["id"] for p in resp.json()}
    assert {p1, p2, p4} <= got
    assert p3 not in got and p5 not in got

    # Membership, not equality: the shared test DB holds other modules'
    # plants too, and their seasons are not this test's business.
    resp = client.get("/api/plants/", params={"season_year": 2026})
    got2026 = {p["id"] for p in resp.json()}
    assert p3 in got2026
    assert not ({p1, p2, p4, p5} & got2026)

    # PATCH can set the explicit override.
    resp = client.patch(f"/api/plants/{p5}", json={"season_year": 2024})
    assert resp.status_code == 200, resp.text
    assert resp.json()["season_year"] == 2024


# --------------------------------------------------------------------------- #
# Minors: generated exclusion + duplicate shots
# --------------------------------------------------------------------------- #
def test_generated_excluded_from_triage_and_yearbook(client):
    with Session(engine) as s:
        album_id = _make_album(s, "LegacyGen", "")
        gen_id = _make_image(s, album_id, fname="g.jpg",
                             original_name="chatgpt-1.jpg",
                             taken_at=datetime(2042, 6, 1, 12, 0, 0),
                             is_generated=True)
        ok_id = _make_image(s, album_id, fname="o.jpg",
                            original_name="ok.jpg",
                            taken_at=datetime(2042, 6, 2, 12, 0, 0))

    resp = client.get("/api/album-images/",
                      params={"album_id": album_id, "unassigned_only": True})
    assert resp.status_code == 200, resp.text
    assert {i["id"] for i in resp.json()} == {ok_id}

    resp = client.get("/api/album-images/", params={"album_id": album_id})
    assert {i["id"] for i in resp.json()} == {gen_id, ok_id}

    with Session(engine) as s:
        picked = yearbook_mod.yearbook_photos(s, 2042)
    picked_names = {p["path"].name for p in picked}
    assert "o.jpg" in picked_names
    assert "g.jpg" not in picked_names


def test_duplicate_shots_endpoint(client):
    with Session(engine) as s:
        album_id = _make_album(s, "LegacyShots", "")
        a = _make_image(s, album_id, fname="a.jpg",
                        taken_at=datetime(2042, 6, 1, 12, 0, 0))
        b = _make_image(s, album_id, fname="b.jpg",
                        taken_at=datetime(2042, 6, 1, 12, 0, 0))
        _make_image(s, album_id, fname="c.jpg",
                    taken_at=datetime(2042, 6, 2, 12, 0, 0))

    resp = client.get(f"/api/albums/{album_id}/duplicate-shots")
    assert resp.status_code == 200, resp.text
    groups = resp.json()
    assert len(groups) == 1
    assert sorted(groups[0]["image_ids"]) == sorted([a, b])
    assert client.get("/api/albums/999999/duplicate-shots").status_code == 404


def test_migration_adds_season_and_generated_columns(tmp_path):
    """Pre-change tables gain season_year / is_generated on startup."""
    db = str(tmp_path / "garden.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE plants (id INTEGER PRIMARY KEY, variety_name TEXT,"
        " species_type TEXT)"
    )
    con.execute(
        "CREATE TABLE album_images (id INTEGER PRIMARY KEY, album_id INTEGER,"
        " file_path TEXT, title TEXT, original_name TEXT, source_url TEXT,"
        " imported_at TEXT, taken_at TEXT, camera_make TEXT, camera_model TEXT,"
        " latitude REAL, longitude REAL)"
    )
    con.commit()
    con.close()

    from sqlmodel import create_engine

    from app.database import _apply_column_migrations

    _apply_column_migrations(create_engine(f"sqlite:///{db}"))
    con = sqlite3.connect(db)
    try:
        plant_cols = {r[1] for r in con.execute("PRAGMA table_info(plants)")}
        image_cols = {r[1] for r in con.execute("PRAGMA table_info(album_images)")}
    finally:
        con.close()
    assert "season_year" in plant_cols
    assert "is_generated" in image_cols


# --------------------------------------------------------------------------- #
# 2.65.1: the is_generated NULL regression (v2.65.0 shipped it)
#
# ALTER TABLE ADD COLUMN leaves existing rows NULL, and the v2.65.0
# AlbumImageRead required a bool — so every album endpoint 500'd on a real
# upgraded database. Sandbox tests never caught it: fresh tables get the
# model default, only an upgraded DB has NULLs. These tests reproduce the
# live failure mode (NULL rows on disk) and the backfill that heals it.
# --------------------------------------------------------------------------- #
def test_album_image_read_coerces_null_generated():
    from types import SimpleNamespace

    from app.schemas import AlbumImageRead

    img = AlbumImageRead.model_validate(
        SimpleNamespace(
            id=1, file_path="/x.jpg", title="t", original_name="o",
            source_url=None, imported_at="2026-09-25T00:00:00",
            taken_at=None, is_generated=None, camera_make=None,
            camera_model=None, latitude=None, longitude=None, tags=None,
            plant_id=None,
        )
    )
    assert img.is_generated is False


def test_albums_endpoint_survives_null_generated(client):
    with Session(engine) as s:
        album_id = _make_album(s, "LegacyNullGen", "")
        img_id = _make_image(s, album_id, fname="n.jpg",
                             original_name="null.jpg")
    # Reproduce the upgraded live DB: the column exists, the row is NULL.
    # On a fresh create_all database the column is NOT NULL, but ALTER
    # TABLE ADD COLUMN on an upgraded DB leaves it nullable — drop and
    # re-add it nullable first, exactly the shape the live DB was in.
    with engine.connect() as conn:
        conn.exec_driver_sql("ALTER TABLE album_images DROP COLUMN is_generated")
        conn.exec_driver_sql("ALTER TABLE album_images ADD COLUMN is_generated BOOLEAN")
        conn.exec_driver_sql(
            "UPDATE album_images SET is_generated = NULL WHERE id = %d" % img_id
        )
        conn.commit()

    resp = client.get(f"/api/albums/{album_id}")
    assert resp.status_code == 200, resp.text
    images = resp.json()["images"]
    assert len(images) == 1
    assert images[0]["is_generated"] is False

    resp = client.get("/api/albums")
    assert resp.status_code == 200, resp.text


def test_migration_backfills_null_generated(tmp_path):
    """Old DBs gain the column AND a 0 for existing rows, in one startup."""
    from sqlmodel import create_engine

    from app.database import _apply_column_migrations

    # Path 1: pre-2.65.0 table without the column at all.
    db = str(tmp_path / "old.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE album_images (id INTEGER PRIMARY KEY, album_id INTEGER,"
        " file_path TEXT)"
    )
    con.execute("INSERT INTO album_images (id, album_id, file_path) VALUES (1, 1, '/x.jpg')")
    con.commit()
    con.close()
    _apply_column_migrations(create_engine(f"sqlite:///{db}"))
    con = sqlite3.connect(db)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(album_images)")}
        val = con.execute("SELECT is_generated FROM album_images WHERE id = 1").fetchone()[0]
    finally:
        con.close()
    assert "is_generated" in cols
    assert val == 0

    # Path 2: column present but NULL (the exact v2.65.0-upgrade state).
    db2 = str(tmp_path / "nulled.db")
    con = sqlite3.connect(db2)
    con.execute(
        "CREATE TABLE album_images (id INTEGER PRIMARY KEY, album_id INTEGER,"
        " file_path TEXT, is_generated INTEGER)"
    )
    con.execute(
        "INSERT INTO album_images (id, album_id, file_path, is_generated)"
        " VALUES (1, 1, '/x.jpg', NULL)"
    )
    con.commit()
    con.close()
    _apply_column_migrations(create_engine(f"sqlite:///{db2}"))
    con = sqlite3.connect(db2)
    try:
        val = con.execute("SELECT is_generated FROM album_images WHERE id = 1").fetchone()[0]
    finally:
        con.close()
    assert val == 0
