"""Photo <-> seed packet matching: assign, unassign, mutual exclusion, filters.

Shares the same temp DB as the other test modules (see test_api.py); every
test cleans up the rows it creates so nothing leaks.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="match-packets-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, delete  # noqa: E402

from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Album, AlbumImage, Plant, SeedPacket  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


CREATED = {"plants": [], "packets": [], "albums": [], "images": []}


@pytest.fixture(autouse=True)
def clean_rows():
    for k in CREATED:
        CREATED[k].clear()
    yield
    with Session(engine) as s:
        if CREATED["images"]:
            s.exec(delete(AlbumImage).where(AlbumImage.id.in_(CREATED["images"])))
        if CREATED["albums"]:
            s.exec(delete(Album).where(Album.id.in_(CREATED["albums"])))
        if CREATED["plants"]:
            s.exec(delete(Plant).where(Plant.id.in_(CREATED["plants"])))
        if CREATED["packets"]:
            s.exec(delete(SeedPacket).where(SeedPacket.id.in_(CREATED["packets"])))
        s.commit()


def _make_plant(session, name="Habanero") -> int:
    plant = Plant(variety_name=name, species_type="Pepper")
    session.add(plant)
    session.commit()
    session.refresh(plant)
    CREATED["plants"].append(plant.id)
    return plant.id


def _make_packet(session, name="Sungold") -> int:
    packet = SeedPacket(variety_name=name, species_type="Tomato", year_acquired=2026)
    session.add(packet)
    session.commit()
    session.refresh(packet)
    CREATED["packets"].append(packet.id)
    return packet.id


def _make_album(session) -> int:
    album = Album(name="A", source_url="immich:AAA")
    session.add(album)
    session.commit()
    session.refresh(album)
    CREATED["albums"].append(album.id)
    return album.id


def _make_image(session, album_id) -> int:
    img = AlbumImage(
        album_id=album_id,
        file_path="/uploads/albums/0/placeholder.jpg",
        title="t",
        source_url="immich:1",
    )
    session.add(img)
    session.commit()
    session.refresh(img)
    CREATED["images"].append(img.id)
    return img.id


def test_assign_photo_to_packet_and_unassign(client):
    with Session(engine) as s:
        pkt_id = _make_packet(s)
        album_id = _make_album(s)
        img_id = _make_image(s, album_id)

    resp = client.patch(f"/api/album-images/{img_id}", json={"seed_packet_id": pkt_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["seed_packet_id"] == pkt_id
    assert body["plant_id"] is None
    assert body["packet_variety"] == "Sungold"

    # Unassign with both null.
    resp = client.patch(f"/api/album-images/{img_id}", json={"seed_packet_id": None, "plant_id": None})
    assert resp.status_code == 200
    body = resp.json()
    assert body["seed_packet_id"] is None and body["plant_id"] is None

    # Bogus packet rejected.
    assert client.patch(f"/api/album-images/{img_id}", json={"seed_packet_id": 999999}).status_code == 404


def test_plant_and_packet_are_mutually_exclusive(client):
    with Session(engine) as s:
        plant_id = _make_plant(s)
        pkt_id = _make_packet(s)
        album_id = _make_album(s)
        img_id = _make_image(s, album_id)

    assert client.patch(f"/api/album-images/{img_id}", json={"plant_id": plant_id}).status_code == 200
    body = client.patch(f"/api/album-images/{img_id}", json={"seed_packet_id": pkt_id}).json()
    assert body["seed_packet_id"] == pkt_id
    assert body["plant_id"] is None, "assigning a packet must clear the plant"

    body = client.patch(f"/api/album-images/{img_id}", json={"plant_id": plant_id}).json()
    assert body["plant_id"] == plant_id
    assert body["seed_packet_id"] is None, "assigning a plant must clear the packet"


def test_packet_filters_and_unassigned_only(client):
    with Session(engine) as s:
        pkt_id = _make_packet(s)
        album_id = _make_album(s)
        i1 = _make_image(s, album_id)
        i2 = _make_image(s, album_id)
        img1 = s.get(AlbumImage, i1)
        img1.seed_packet_id = pkt_id
        s.add(img1)
        s.commit()

    un = client.get("/api/album-images/", params={"unassigned_only": "true"}).json()
    ids = {i["id"] for i in un}
    assert i2 in ids and i1 not in ids, "packet-assigned photo must leave the unassigned view"

    by_packet = client.get("/api/album-images/", params={"seed_packet_id": pkt_id}).json()
    assert [i["id"] for i in by_packet] == [i1]
    assert by_packet[0]["packet_variety"] == "Sungold"


def test_bulk_assign_to_packet(client):
    with Session(engine) as s:
        pkt_id = _make_packet(s, "Marketmore")
        album_id = _make_album(s)
        imgs = [_make_image(s, album_id) for _ in range(2)]

    resp = client.post(
        "/api/album-images/bulk-assign",
        json={"image_ids": imgs, "seed_packet_id": pkt_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 2}

    got = client.get("/api/album-images/", params={"seed_packet_id": pkt_id}).json()
    assert {i["id"] for i in got} == set(imgs)
    assert all(i["plant_id"] is None for i in got)

    assert client.post(
        "/api/album-images/bulk-assign",
        json={"image_ids": imgs, "seed_packet_id": 999999},
    ).status_code == 404
