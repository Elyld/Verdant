"""End-to-end API tests (in-memory-ish: temp dirs per run).

Run with:  pytest -q      (needs pytest + httpx installed)
"""
from __future__ import annotations

import io
import os
import struct
import tempfile
import zlib
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="garden-test-"))
os.environ["GARDEN_DATA_DIR"] = str(TMP / "data")
os.environ["GARDEN_UPLOAD_DIR"] = str(TMP / "uploads")
os.environ["GARDEN_DATABASE_URL"] = f"sqlite:///{TMP / 'test.db'}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


def png_bytes(width: int = 4, height: int = 4) -> bytes:
    """Minimal valid PNG, generated without external deps."""

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


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Verdant" in res.text


def test_post_crud_and_images(client):
    created = client.post(
        "/api/posts", json={"title": "First tomatoes", "content": "## Week 12\n\n**Brandywines** set fruit."}
    )
    assert created.status_code == 201, created.text
    post = created.json()
    assert post["title"] == "First tomatoes"
    assert post["images"] == []

    # upload two images
    files = [
        ("files", ("a.png", io.BytesIO(png_bytes()), "image/png")),
        ("files", ("b.png", io.BytesIO(png_bytes()), "image/png")),
    ]
    up = client.post(f"/api/posts/{post['id']}/images", files=files)
    assert up.status_code == 201, up.text
    images = up.json()["images"]
    assert len(images) == 2

    # files exist on disk and are served
    for img in images:
        assert img["file_path"].startswith("/uploads/posts/")
        assert client.get(img["file_path"]).status_code == 200

    # read back with images attached
    fetched = client.get(f"/api/posts/{post['id']}").json()
    assert len(fetched["images"]) == 2

    # patch
    patched = client.patch(f"/api/posts/{post['id']}", json={"title": "First ripe tomatoes"})
    assert patched.status_code == 200
    assert patched.json()["title"] == "First ripe tomatoes"

    # search
    assert any(p["id"] == post["id"] for p in client.get("/api/posts?q=ripe").json())
    assert client.get("/api/posts?q=zzzznotfound").json() == []

    # delete image, then post; files are cleaned up
    stored = [
        Path(os.environ["GARDEN_UPLOAD_DIR"]) / img["file_path"].removeprefix("/uploads/")
        for img in images
    ]
    assert client.delete(f"/api/posts/{post['id']}/images/{images[0]['id']}").status_code == 204
    assert not stored[0].exists()

    assert client.delete(f"/api/posts/{post['id']}").status_code == 204
    assert not stored[1].exists()
    assert client.get(f"/api/posts/{post['id']}").status_code == 404


def test_rejects_non_image_upload(client):
    post = client.post("/api/posts", json={"title": "bad upload"}).json()
    res = client.post(
        f"/api/posts/{post['id']}/images",
        files=[("files", ("evil.png", io.BytesIO(b"#!/bin/sh\nrm -rf /"), "image/png"))],
    )
    assert res.status_code == 415
    assert client.get(f"/api/posts/{post['id']}").json()["images"] == []


def test_upload_filename_is_not_client_controlled(client):
    post = client.post("/api/posts", json={"title": "traversal"}).json()
    res = client.post(
        f"/api/posts/{post['id']}/images",
        files=[("files", ("../../../../etc/passwd.png", io.BytesIO(png_bytes()), "image/png"))],
    )
    assert res.status_code == 201
    path = res.json()["images"][0]["file_path"]
    assert ".." not in path
    assert path.startswith(f"/uploads/posts/{post['id']}/")


def test_fertilization_crud(client):
    res = client.post(
        "/api/fertilizations",
        json={
            "date": "2026-05-02",
            "fertilizer_name": "Fish emulsion",
            "npk_ratio": "5-1-1",
            "amount_used": "2 tbsp/gal",
            "notes": "Bed 2",
        },
    )
    assert res.status_code == 201, res.text
    log = res.json()
    assert log["npk_ratio"] == "5-1-1"

    assert client.patch(f"/api/fertilizations/{log['id']}", json={"amount_used": "3 tbsp/gal"}).json()[
        "amount_used"
    ] == "3 tbsp/gal"
    assert any(f["id"] == log["id"] for f in client.get("/api/fertilizations").json())
    assert client.delete(f"/api/fertilizations/{log['id']}").status_code == 204
    assert client.get(f"/api/fertilizations/{log['id']}").status_code == 404


def test_observation_crud_with_images_and_filter(client):
    res = client.post(
        "/api/observations",
        json={
            "date": "2026-05-03",
            "plant_name": "Brandywine tomato",
            "health_scale": 8,
            "watering_status": True,
            "pest_sightings": "aphids",
            "notes": "new growth",
        },
    )
    assert res.status_code == 201, res.text
    obs = res.json()
    assert obs["health_scale"] == 8 and obs["watering_status"] is True

    up = client.post(
        f"/api/observations/{obs['id']}/images",
        files=[("files", ("leaf.png", io.BytesIO(png_bytes()), "image/png"))],
    )
    assert up.status_code == 201
    assert len(client.get(f"/api/observations/{obs['id']}").json()["images"]) == 1

    assert any(o["id"] == obs["id"] for o in client.get("/api/observations?plant=brandywine").json())
    assert client.get("/api/observations?plant=nosuchplant").json() == []

    # health_scale bounds are enforced
    bad = client.post(
        "/api/observations",
        json={"date": "2026-05-03", "plant_name": "x", "health_scale": 42},
    )
    assert bad.status_code == 422

    assert client.delete(f"/api/observations/{obs['id']}").status_code == 204


def test_stats(client):
    client.post("/api/posts", json={"title": "stats post", "content": "hi"})
    client.post(
        "/api/observations",
        json={"date": "2026-06-01", "plant_name": "Basil", "health_scale": 6, "watering_status": True},
    )
    client.post("/api/fertilizations", json={"date": "2026-06-01", "fertilizer_name": "Kelp"})

    stats = client.get("/api/stats").json()
    assert stats["posts"] >= 1
    assert stats["observations"] >= 1
    assert stats["fertilizations"] >= 1
    assert 1 <= stats["avg_health"] <= 10
    assert stats["last_watered"] == "2026-06-01"


def test_404s(client):
    assert client.get("/api/posts/999999").status_code == 404
    assert client.get("/api/observations/999999").status_code == 404
    assert client.get("/api/fertilizations/999999").status_code == 404
