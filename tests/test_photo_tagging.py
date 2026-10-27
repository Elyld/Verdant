"""Photo tagging & attribution tests (tags, notes, container links, and the
section-7 smaller items: container grid placement, Culled status, unset
health, pest resolved-date/severity, Immich sync-all + batch contract fix,
duplicate-album-name banner).

Shares the same temp DB as the other test modules (see test_match.py);
every test cleans up the rows it creates so nothing leaks.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="tagging-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, delete  # noqa: E402

from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Album, AlbumImage, Container, Plant  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


CREATED = {"plants": [], "albums": [], "images": [], "containers": []}


@pytest.fixture(autouse=True)
def clean_tagging_rows():
    for key in CREATED:
        CREATED[key].clear()
    yield
    with Session(engine) as s:
        if CREATED["images"]:
            s.exec(delete(AlbumImage).where(AlbumImage.id.in_(CREATED["images"])))
        if CREATED["containers"]:
            s.exec(delete(Container).where(Container.id.in_(CREATED["containers"])))
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


def _make_image(session, album_id, source_url="") -> int:
    img = AlbumImage(
        album_id=album_id,
        file_path="/uploads/albums/0/placeholder.jpg",
        title="t",
        source_url=source_url,
    )
    session.add(img)
    session.commit()
    session.refresh(img)
    CREATED["images"].append(img.id)
    return img.id


def _make_container(session, name="Bed 1", year=None) -> int:
    container = Container(name=name, kind="raised bed", season_year=year or date.today().year)
    session.add(container)
    session.commit()
    session.refresh(container)
    CREATED["containers"].append(container.id)
    return container.id


# ---------------------------------------------------------------------------
# Tags / notes / container link on album images
# ---------------------------------------------------------------------------


def test_patch_tags_notes_container_independent_of_plant(client):
    with Session(engine) as s:
        plant_id = _make_plant(s)
        album_id = _make_album(s)
        img_id = _make_image(s, album_id)
        container_id = _make_container(s)

    r = client.patch(f"/api/album-images/{img_id}", json={"plant_id": plant_id})
    assert r.status_code == 200, r.text
    assert r.json()["plant_id"] == plant_id

    # Tags + notes + container on their own must NOT disturb the plant link.
    r = client.patch(
        f"/api/album-images/{img_id}",
        json={
            "tags": [" Seed-Starting ", "flower", "flower", ""],
            "notes": "First tray under lights",
            "container_id": container_id,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plant_id"] == plant_id
    assert body["tags"] == "seed-starting, flower"  # normalized: lower, deduped
    assert body["notes"] == "First tray under lights"
    assert body["container_id"] == container_id
    assert body["container_name"] == "Bed 1"

    # Clearing tags leaves everything else alone.
    r = client.patch(f"/api/album-images/{img_id}", json={"tags": []})
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ""
    assert r.json()["plant_id"] == plant_id
    assert r.json()["container_id"] == container_id


def test_bulk_tags_only_keeps_plant_links(client):
    with Session(engine) as s:
        plant_id = _make_plant(s)
        album_id = _make_album(s)
        a = _make_image(s, album_id, "immich:bulk-a")
        b = _make_image(s, album_id, "immich:bulk-b")

    assert client.patch(f"/api/album-images/{a}", json={"plant_id": plant_id}).status_code == 200
    assert client.patch(f"/api/album-images/{b}", json={"plant_id": plant_id}).status_code == 200

    r = client.post(
        "/api/album-images/bulk-assign", json={"image_ids": [a, b], "tags": ["harvest"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2

    rows = client.get(f"/api/album-images/?album_id={album_id}&limit=100").json()
    by_id = {row["id"]: row for row in rows}
    assert by_id[a]["tags"] == "harvest" and by_id[a]["plant_id"] == plant_id
    assert by_id[b]["tags"] == "harvest" and by_id[b]["plant_id"] == plant_id


def test_bulk_plant_assign_and_explicit_unassign_still_work(client):
    with Session(engine) as s:
        plant_id = _make_plant(s)
        album_id = _make_album(s)
        a = _make_image(s, album_id, "immich:bulk-c")

    r = client.post(
        "/api/album-images/bulk-assign", json={"image_ids": [a], "plant_id": plant_id}
    )
    assert r.status_code == 200
    assert client.get(f"/api/album-images/?album_id={album_id}").json()[0]["plant_id"] == plant_id

    r = client.post(
        "/api/album-images/bulk-assign",
        json={"image_ids": [a], "plant_id": None, "seed_packet_id": None},
    )
    assert r.status_code == 200
    assert client.get(f"/api/album-images/?album_id={album_id}").json()[0]["plant_id"] is None


def test_tag_filter_is_exact_token_case_insensitive(client):
    with Session(engine) as s:
        album_id = _make_album(s)
        a = _make_image(s, album_id, "immich:tag-a")
        b = _make_image(s, album_id, "immich:tag-b")
        c = _make_image(s, album_id, "immich:tag-c")

    client.patch(f"/api/album-images/{a}", json={"tags": ["flower"]})
    client.patch(f"/api/album-images/{b}", json={"tags": ["flowers"]})
    client.patch(f"/api/album-images/{c}", json={"tags": ["flower", "harvest"]})

    got = client.get(f"/api/album-images/?album_id={album_id}&tag=flower").json()
    assert {row["id"] for row in got} == {a, c}  # "flowers" must not match
    got = client.get(f"/api/album-images/?album_id={album_id}&tag=FLOWER").json()
    assert {row["id"] for row in got} == {a, c}
    got = client.get(f"/api/album-images/?album_id={album_id}&tag=harvest").json()
    assert {row["id"] for row in got} == {c}


def test_tag_filter_by_container(client):
    with Session(engine) as s:
        album_id = _make_album(s)
        a = _make_image(s, album_id, "immich:cont-a")
        b = _make_image(s, album_id, "immich:cont-b")
        container_id = _make_container(s)

    client.patch(f"/api/album-images/{a}", json={"container_id": container_id})
    got = client.get(f"/api/album-images/?container_id={container_id}").json()
    assert {row["id"] for row in got} == {a}
    assert got[0]["container_name"] == "Bed 1"


def test_vocabulary_endpoint(client):
    body = client.get("/api/album-images/vocabulary").json()
    tags = [entry["tag"] for entry in body["tags"]]
    assert tags == [
        "seed-starting",
        "flower",
        "plan",
        "harvest",
        "wide-shot",
        "soil-prep",
        "pest-disease",
        "supplies",
        "structure",
        "unidentified",
    ]
    assert all(entry["description"] for entry in body["tags"])


# ---------------------------------------------------------------------------
# Section 7 smaller items
# ---------------------------------------------------------------------------


def test_container_post_honours_grid_and_rejects_overlap(client):
    year = date.today().year
    r = client.post(
        "/api/containers/",
        json={"name": "Grid Bed A", "kind": "raised bed", "season_year": year,
              "grid_x": 0, "grid_y": 0, "grid_w": 1, "grid_h": 1},
    )
    assert r.status_code == 201, r.text
    assert (r.json()["grid_x"], r.json()["grid_y"]) == (0, 0)
    CREATED["containers"].append(r.json()["id"])

    # Same cell, same season: collision, not a silent second card.
    r = client.post(
        "/api/containers/",
        json={"name": "Grid Bed B", "kind": "raised bed", "season_year": year,
              "grid_x": 0, "grid_y": 0, "grid_w": 1, "grid_h": 1},
    )
    assert r.status_code == 422, r.text

    # No coords: still auto-placed as before.
    r = client.post(
        "/api/containers/",
        json={"name": "Grid Bed C", "kind": "grow bag", "season_year": year},
    )
    assert r.status_code == 201, r.text
    assert r.json()["grid_x"] is not None and r.json()["grid_y"] is not None
    CREATED["containers"].append(r.json()["id"])


def test_plant_culled_status_and_status_date(client):
    with Session(engine) as s:
        plant_id = _make_plant(s)

    r = client.patch(f"/api/plants/{plant_id}", json={"status": "Culled"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Culled"
    assert r.json()["status_changed_at"] == date.today().isoformat()

    # Re-saving the same status, or another field, does not re-stamp.
    r = client.patch(f"/api/plants/{plant_id}", json={"status": "Culled"})
    assert r.json()["status_changed_at"] == date.today().isoformat()
    r = client.patch(f"/api/plants/{plant_id}", json={"notes": "thinned for airflow"})
    assert r.json()["status"] == "Culled"
    assert r.json()["status_changed_at"] == date.today().isoformat()


def test_observation_health_unset_instead_of_default_5(client):
    r = client.post(
        "/api/observations",
        json={"date": date.today().isoformat(), "plant_name": "No Opinion Pepper"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["health_scale"] is None

    r = client.post(
        "/api/observations",
        json={"date": date.today().isoformat(), "plant_name": "Rated Pepper", "health_scale": 7},
    )
    assert r.status_code == 201, r.text
    assert r.json()["health_scale"] == 7


def test_pest_resolve_stamps_date_and_severity_round_trips(client):
    r = client.post(
        "/api/pests/",
        json={"date": date.today().isoformat(), "pest_name": "Aphids", "severity": "High"},
    )
    assert r.status_code == 201, r.text
    pest_id = r.json()["id"]
    assert r.json()["severity"] == "High"
    assert r.json()["resolved_date"] is None

    r = client.patch(f"/api/pests/{pest_id}", json={"resolved": True})
    assert r.status_code == 200, r.text
    assert r.json()["resolved"] is True
    assert r.json()["resolved_date"] == date.today().isoformat()

    r = client.patch(f"/api/pests/{pest_id}", json={"resolved": False})
    assert r.json()["resolved"] is False
    assert r.json()["resolved_date"] is None


def test_duplicate_names_endpoint(client):
    with Session(engine) as s:
        a = _make_album(s, "Dupe Name X")
        b = _make_album(s, "Dupe Name X")
        _make_album(s, "Unique Name X")

    groups = client.get("/api/albums/duplicate-names").json()
    match = [g for g in groups if g["name"] == "Dupe Name X"]
    assert len(match) == 1
    assert set(match[0]["album_ids"]) >= {a, b}
    assert not [g for g in groups if g["name"] == "Unique Name X"]


# ---------------------------------------------------------------------------
# Immich: batch contract fix + sync-all
# ---------------------------------------------------------------------------

JPEG = bytes.fromhex("ffd8ffe000104a4649460001010000010001000000") + b"\x00" * 64


def _stub_immich(monkeypatch, album_name="Tagging Garden"):
    import app.routers.immich as immich_router

    monkeypatch.setattr(
        immich_router.immich, "get_album",
        lambda _id: {"id": _id, "albumName": album_name, "assetCount": 4},
    )
    monkeypatch.setattr(
        immich_router.immich, "list_album_assets",
        lambda _id: [
            {"id": f"p{i}", "type": "IMAGE", "originalFileName": f"pic{i}.jpg"}
            for i in range(4)
        ],
    )
    monkeypatch.setattr(immich_router.immich, "download_asset", lambda _id: JPEG)


def test_immich_offset_without_album_id_resolves(client, monkeypatch):
    _stub_immich(monkeypatch)
    first = client.post("/api/immich/albums/tagged/import?offset=0&limit=2")
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["total"], body["created"], body["done"]) == (4, 2, False)
    CREATED["albums"].append(body["album_id"])
    CREATED["images"].extend(
        row["id"]
        for row in client.get(f"/api/albums/{body['album_id']}").json()["images"]
    )

    # The old contract 400'd here; now the local album resolves by source_url.
    second = client.post("/api/immich/albums/tagged/import?offset=2&limit=2")
    assert second.status_code == 200, second.text
    assert (second.json()["created"], second.json()["done"]) == (2, True)
    assert second.json()["album_id"] == body["album_id"]
    assert client.get(f"/api/albums/{body['album_id']}").json()["last_synced_at"] is not None


def test_immich_sync_all_sets_last_synced_at(client, monkeypatch):
    _stub_immich(monkeypatch, album_name="Sync Garden")
    with Session(engine) as s:
        album_id = _make_album(s, "Sync Garden", "immich:syncme")

    r = client.post("/api/immich/albums/sync-all")
    assert r.status_code == 200, r.text
    mine = [a for a in r.json()["albums"] if a["album_id"] == album_id]
    assert len(mine) == 1
    assert mine[0]["done"] is True
    assert mine[0]["created"] == 4
    assert client.get(f"/api/albums/{album_id}").json()["last_synced_at"] is not None
