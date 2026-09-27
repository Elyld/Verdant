"""Seed packet library-photo attach tests: POST /api/seed-packets/{id}/photo-from-library.

Covers: attach front/back from an existing album image (copy semantics),
replacing a side deletes the old copy, the source image is never touched,
and 404/422 paths.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="pktlib-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.database import UPLOAD_DIR, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Album, AlbumImage  # noqa: E402

JPEG = b"\xff\xd8\xff" + b"\x00" * 64


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def library_image(client):
    album = client.post("/api/albums/", data={"name": "Packet pics"}).json()["album"]
    src_dir = UPLOAD_DIR / "albums" / str(album["id"])
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "habanero.jpg").write_bytes(JPEG)
    with Session(engine) as s:
        s.add(
            AlbumImage(
                album_id=album["id"],
                file_path=f"/uploads/albums/{album['id']}/habanero.jpg",
                title="Habanero packet",
            )
        )
        s.commit()
        img = s.exec(select(AlbumImage)).first()
        return img.id


@pytest.fixture(scope="module")
def packet(client):
    return client.post("/api/seed-packets/", json={"variety_name": "Habanero"}).json()


def _stored(rel_url: str) -> Path:
    assert rel_url.startswith("/uploads/")
    return UPLOAD_DIR / rel_url[len("/uploads/") :]


def test_attach_front_copies_source(client, packet, library_image):
    src = UPLOAD_DIR / "albums" / "1" / "habanero.jpg"
    res = client.post(
        f"/api/seed-packets/{packet['id']}/photo-from-library",
        json={"image_id": library_image, "side": "front"},
    )
    assert res.status_code == 200
    url = res.json()["photo_path"]
    assert url.startswith(f"/uploads/seed-packets/{packet['id']}/")
    assert url != f"/uploads/albums/1/habanero.jpg"
    assert _stored(url).exists()
    assert src.exists()  # source untouched


def test_replace_front_deletes_old_copy(client, packet, library_image):
    first = client.get("/api/seed-packets/").json()
    old_url = next(p["photo_path"] for p in first if p["id"] == packet["id"])
    res = client.post(
        f"/api/seed-packets/{packet['id']}/photo-from-library",
        json={"image_id": library_image, "side": "front"},
    )
    assert res.status_code == 200
    new_url = res.json()["photo_path"]
    assert new_url != old_url
    assert not _stored(old_url).exists()
    assert _stored(new_url).exists()


def test_attach_back(client, packet, library_image):
    res = client.post(
        f"/api/seed-packets/{packet['id']}/photo-from-library",
        json={"image_id": library_image, "side": "back"},
    )
    assert res.status_code == 200
    assert res.json()["photo_back_path"].startswith(
        f"/uploads/seed-packets/{packet['id']}/"
    )


def test_unknown_image_404(client, packet):
    res = client.post(
        f"/api/seed-packets/{packet['id']}/photo-from-library",
        json={"image_id": 424242, "side": "front"},
    )
    assert res.status_code == 404


def test_unknown_packet_404(client, library_image):
    res = client.post(
        "/api/seed-packets/424242/photo-from-library",
        json={"image_id": library_image, "side": "front"},
    )
    assert res.status_code == 404


def test_bad_side_422(client, packet, library_image):
    res = client.post(
        f"/api/seed-packets/{packet['id']}/photo-from-library",
        json={"image_id": library_image, "side": "sideways"},
    )
    assert res.status_code == 422


def test_seeds_page_has_picker_and_filter(client):
    res = client.get("/seeds")
    assert res.status_code == 200
    assert 'id="library-modal"' in res.text
    assert 'id="catalog-photo"' in res.text
    assert 'id="packet-library-front"' in res.text
