"""Plant <-> seed packet linking: create, PATCH, and bad-packet rejection.

Run with:  pytest -q
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="plant-packet-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    created = {"plants": [], "packets": []}
    with TestClient(app) as c:
        yield c, created
    with TestClient(app) as c:
        for plant_id in created["plants"]:
            c.delete(f"/api/plants/{plant_id}")
        for pkt_id in created["packets"]:
            c.delete(f"/api/seed-packets/{pkt_id}")


def test_plant_links_to_packet_on_create_and_patch(client):
    c, created = client
    res = c.post("/api/seed-packets/", json={"variety_name": "LinkTest Pepper"})
    assert res.status_code == 201, res.text
    pkt_id = res.json()["id"]
    created["packets"].append(pkt_id)

    res = c.post("/api/plants/", json={
        "variety_name": "LinkTest Plant",
        "species_type": "Pepper",
        "seed_packet_id": pkt_id,
    })
    assert res.status_code == 201, res.text
    plant_id = res.json()["id"]
    created["plants"].append(plant_id)
    assert res.json()["seed_packet_id"] == pkt_id

    # Unlink via PATCH.
    res = c.patch(f"/api/plants/{plant_id}", json={"seed_packet_id": None})
    assert res.status_code == 200
    assert res.json()["seed_packet_id"] is None

    # Relink via PATCH.
    res = c.patch(f"/api/plants/{plant_id}", json={"seed_packet_id": pkt_id})
    assert res.status_code == 200
    assert res.json()["seed_packet_id"] == pkt_id

    # GET reflects the link.
    res = c.get(f"/api/plants/{plant_id}")
    assert res.json()["seed_packet_id"] == pkt_id


def test_plant_rejects_unknown_packet(client):
    c, created = client
    res = c.post("/api/seed-packets/", json={"variety_name": "LinkTest Pepper 2"})
    assert res.status_code == 201, res.text
    pkt_id = res.json()["id"]
    created["packets"].append(pkt_id)

    res = c.post("/api/plants/", json={
        "variety_name": "Bad Link Plant",
        "species_type": "Pepper",
        "seed_packet_id": 999999,
    })
    assert res.status_code == 404

    res = c.post("/api/plants/", json={
        "variety_name": "Bad Link Plant 2",
        "species_type": "Pepper",
    })
    assert res.status_code == 201, res.text
    plant_id = res.json()["id"]
    created["plants"].append(plant_id)

    res = c.patch(f"/api/plants/{plant_id}", json={"seed_packet_id": 999999})
    assert res.status_code == 404
