"""Photo <-> plant matching + Immich album dedup tests.

Shares the same temp DB as the other test modules (see test_api.py); every
test cleans up the rows it creates so nothing leaks.
"""
from __future__ import annotations

import os
import sqlite3
import struct
import tempfile
import zlib
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="match-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, delete, select  # noqa: E402

from app.database import UPLOAD_DIR, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Album, AlbumImage, Plant  # noqa: E402
from app.routers.immich import _asset_metadata, _tag_names  # noqa: E402
from app.schemas import AlbumImageRead  # noqa: E402
from types import SimpleNamespace  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


CREATED = {"plants": [], "albums": [], "images": []}


@pytest.fixture(autouse=True)
def clean_match_rows():
    CREATED["plants"].clear()
    CREATED["albums"].clear()
    CREATED["images"].clear()
    yield
    with Session(engine) as s:
        if CREATED["images"]:
            s.exec(delete(AlbumImage).where(AlbumImage.id.in_(CREATED["images"])))
        if CREATED["albums"]:
            s.exec(delete(Album).where(Album.id.in_(CREATED["albums"])))
        if CREATED["plants"]:
            s.exec(delete(Plant).where(Plant.id.in_(CREATED["plants"])))
        s.commit()


def _make_plant(session, name="Habanero") -> int:
    plant = Plant(variety_name=name, species_type="Pepper")
    session.add(plant)
    session.commit()
    session.refresh(plant)
    CREATED["plants"].append(plant.id)
    return plant.id


def _make_album(session, name="A", source_url="") -> int:
    album = Album(name=name, source_url=source_url)
    session.add(album)
    session.commit()
    session.refresh(album)
    CREATED["albums"].append(album.id)
    return album.id


def _make_image(session, album_id, source_url="", with_file=False) -> int:
    if with_file:
        target = UPLOAD_DIR / f"albums/{album_id}"
        target.mkdir(parents=True, exist_ok=True)
        fname = f"img-{source_url.replace(':', '-') or 'x'}.jpg"
        (target / fname).write_bytes(b"fake-bytes")
        file_path = f"/uploads/albums/{album_id}/{fname}"
    else:
        file_path = "/uploads/albums/0/placeholder.jpg"
    img = AlbumImage(
        album_id=album_id,
        file_path=file_path,
        title="t",
        source_url=source_url,
    )
    session.add(img)
    session.commit()
    session.refresh(img)
    img_id = img.id
    CREATED["images"].append(img_id)
    return img_id


def test_assign_and_unassign_photo(client):
    with Session(engine) as s:
        plant_id = _make_plant(s)
        album_id = _make_album(s, "A", "immich:AAA")
        img_id = _make_image(s, album_id, "immich:1")

    resp = client.patch(f"/api/album-images/{img_id}", json={"plant_id": plant_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plant_id"] == plant_id
    assert body["plant_variety"] == "Habanero"

    resp = client.patch(f"/api/album-images/{img_id}", json={"plant_id": None})
    assert resp.status_code == 200
    assert resp.json()["plant_id"] is None

    assert client.patch("/api/album-images/999999", json={"plant_id": plant_id}).status_code == 404
    assert client.patch(f"/api/album-images/{img_id}", json={"plant_id": 999999}).status_code == 404


def test_list_filters(client):
    with Session(engine) as s:
        plant_id = _make_plant(s)
        a = _make_album(s, "A", "immich:AAA")
        b = _make_album(s, "B", "immich:BBB")
        i1 = _make_image(s, a, "immich:1")
        i2 = _make_image(s, a, "immich:2")
        i3 = _make_image(s, b, "immich:3")
        img1 = s.get(AlbumImage, i1)
        img1.plant_id = plant_id
        s.add(img1)
        s.commit()

    un = client.get("/api/album-images/", params={"unassigned_only": "true"}).json()
    ids = {i["id"] for i in un}
    assert i2 in ids and i3 in ids and i1 not in ids

    by_plant = client.get("/api/album-images/", params={"plant_id": plant_id}).json()
    assert [i["id"] for i in by_plant] == [i1]
    assert by_plant[0]["plant_variety"] == "Habanero"

    by_album = client.get("/api/album-images/", params={"album_id": b}).json()
    assert [i["id"] for i in by_album] == [i3]


def test_bulk_assign(client):
    with Session(engine) as s:
        plant_id = _make_plant(s, "Sungold")
        album_id = _make_album(s)
        imgs = [_make_image(s, album_id, f"bulk:{n}") for n in range(3)]

    resp = client.post(
        "/api/album-images/bulk-assign",
        json={"image_ids": [imgs[0], imgs[1], imgs[1]], "plant_id": plant_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 2}

    got = client.get("/api/album-images/", params={"plant_id": plant_id}).json()
    assert {i["id"] for i in got} == {imgs[0], imgs[1]}

    resp = client.post(
        "/api/album-images/bulk-assign",
        json={"image_ids": [imgs[0], imgs[1]], "plant_id": None},
    )
    assert resp.json() == {"updated": 2}
    assert client.post(
        "/api/album-images/bulk-assign",
        json={"image_ids": [imgs[0]], "plant_id": 999999},
    ).status_code == 404


def test_merge_duplicate_albums(client):
    with Session(engine) as s:
        keeper_id = _make_album(s, "Plants 2025", "immich:AAA")
        dupe_id = _make_album(s, "Plants 2025", "immich:AAA")
        _make_album(s, "Other", "immich:ZZZ")
        _make_album(s, "Local snaps", "")
        _make_image(s, keeper_id, "immich:1", with_file=True)
        _make_image(s, keeper_id, "immich:2", with_file=True)
        d_dup_id = _make_image(s, dupe_id, "immich:2", with_file=True)  # true dupe
        d_unique_id = _make_image(s, dupe_id, "immich:3", with_file=True)  # unique: moves
        d_dup = s.get(AlbumImage, d_dup_id)
        dupe_file = UPLOAD_DIR / d_dup.file_path[len("/uploads/"):]
        assert dupe_file.exists()

    resp = client.post("/api/albums/merge-duplicates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["groups_merged"] == 1
    assert body["albums_removed"] == 1
    assert body["images_moved"] == 1
    assert body["files_removed"] == 1
    # The re-downloaded duplicate bytes are gone from disk…
    assert not dupe_file.exists()
    # …the unique photo moved to the keeper, and the others are untouched.
    with Session(engine) as s:
        remaining = s.exec(select(Album)).all()
        names = sorted(a.name for a in remaining)
        assert names == ["Local snaps", "Other", "Plants 2025"]
        kept = s.exec(select(Album).where(Album.name == "Plants 2025")).one()
        kept_sources = sorted(i.source_url for i in kept.images)
        assert kept_sources == ["immich:1", "immich:2", "immich:3"]
        moved = s.get(AlbumImage, d_unique_id)
        assert moved.album_id == kept.id
        assert (UPLOAD_DIR / moved.file_path[len("/uploads/"):]).exists()

    # Second run finds nothing to do.
    again = client.post("/api/albums/merge-duplicates").json()
    assert again["groups_merged"] == 0


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


def test_import_reuses_existing_album_and_captures_tags(client, monkeypatch):
    assets = [
        {
            "id": "a1",
            "type": "IMAGE",
            "originalFileName": "pepper.jpg",
            "fileCreatedAt": "2026-09-20T10:00:00Z",
            "exifInfo": {
                "dateTimeOriginal": "2026-09-20T10:00:00Z",
                "make": "Google",
                "model": "Pixel",
                "latitude": 39.1,
                "longitude": -94.5,
            },
            "tags": [{"name": "pepper"}, {"name": "habanero"}],
        }
    ]
    monkeypatch.setattr("app.immich.get_album", lambda album_id: {"albumName": "Plants 2025"})
    monkeypatch.setattr("app.immich.list_album_assets", lambda album_id: assets)
    monkeypatch.setattr("app.immich.download_asset", lambda asset_id: _png_bytes())

    first = client.post("/api/immich/albums/ABC123/import", params={"offset": 0, "limit": 50})
    assert first.status_code == 200, first.text
    album_id = first.json()["album_id"]
    assert first.json()["created"] == 1
    CREATED["albums"].append(album_id)

    # Re-importing the same Immich album lands in the same local album…
    second = client.post("/api/immich/albums/ABC123/import", params={"offset": 0, "limit": 50})
    assert second.status_code == 200, second.text
    assert second.json()["album_id"] == album_id
    assert second.json()["created"] == 0  # …and the photo is skipped, not duplicated.

    with Session(engine) as s:
        albums = s.exec(select(Album).where(Album.source_url == "immich:ABC123")).all()
        assert len(albums) == 1
        imgs = s.exec(select(AlbumImage).where(AlbumImage.album_id == album_id)).all()
        assert len(imgs) == 1
        # XMP sidecar keywords arrived as Immich tags.
        assert imgs[0].tags == "pepper, habanero"
        assert imgs[0].latitude == 39.1
        CREATED["images"].extend(i.id for i in imgs)


def test_tag_names_handles_shapes():
    assert _tag_names(None) == ""
    assert _tag_names([]) == ""
    assert _tag_names([{"name": "pepper"}, {"name": "Pepper"}, "  habanero "]) == "pepper, habanero"
    assert _tag_names([{"value": "xmp-tag"}]) == "xmp-tag"
    assert _tag_names(["a", None, 5]) == "a, 5"


def test_asset_metadata_pulls_tags():
    meta = _asset_metadata({"id": "x", "tags": [{"name": "pepper"}], "exifInfo": {}})
    assert meta["tags"] == "pepper"


def test_null_tags_serialize_cleanly():
    img = AlbumImageRead.model_validate(
        SimpleNamespace(
            id=1, file_path="/x.jpg", title="t", original_name="o",
            source_url=None, imported_at="2026-09-25T00:00:00",
            taken_at=None, camera_make=None, camera_model=None,
            latitude=None, longitude=None, tags=None, plant_id=None,
        )
    )
    assert img.tags == ""


def test_migration_adds_match_columns(tmp_path):
    """A pre-2.9.0 album_images table gains plant_id/tags on startup."""
    db = str(tmp_path / "garden.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE album_images (id INTEGER PRIMARY KEY, album_id INTEGER,"
        " file_path TEXT, title TEXT, original_name TEXT, source_url TEXT,"
        " imported_at TEXT, taken_at TEXT, camera_make TEXT, camera_model TEXT,"
        " latitude REAL, longitude REAL)"
    )
    con.execute(
        "INSERT INTO album_images (album_id, file_path) VALUES (1, '/uploads/a.jpg')"
    )
    con.commit()
    con.close()

    from sqlmodel import create_engine

    from app.database import _apply_column_migrations

    _apply_column_migrations(create_engine(f"sqlite:///{db}"))
    con = sqlite3.connect(db)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(album_images)")}
    finally:
        con.close()
    assert "plant_id" in cols
    assert "tags" in cols
