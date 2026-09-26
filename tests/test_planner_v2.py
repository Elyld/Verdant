"""Planner 2.0: grid system, multi-plant containers, rotation warnings.

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="planner2-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _plant(variety, species="Capsicum chinense", family="Solanaceae"):
    r = client.post("/api/plants/", json={
        "variety_name": variety, "species_type": species, "family_genus": family})
    assert r.status_code == 201, r.text
    return r.json()


def _container(name, kind="grow bag", year=2035, **kw):
    payload = {"name": name, "kind": kind, "season_year": year}
    payload.update(kw)
    r = client.post("/api/containers/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Grid system
# --------------------------------------------------------------------------- #
def test_grid_defaults_and_resize():
    r = client.get("/api/containers/grid")
    assert r.status_code == 200
    assert r.json() == {"cols": 24, "rows": 16}

    r = client.put("/api/containers/grid", json={"cols": 30, "rows": 20})
    assert r.status_code == 200 and r.json() == {"cols": 30, "rows": 20}

    r = client.put("/api/containers/grid", json={"cols": 2, "rows": 200})
    assert r.status_code == 422

    # restore defaults for the other tests
    r = client.put("/api/containers/grid", json={"cols": 24, "rows": 16})
    assert r.status_code == 200


def test_container_gets_grid_placement_and_footprint():
    c = _container("Grid Bag 1", kind="grow bag", year=2035)
    assert c["grid_w"] == 2 and c["grid_h"] == 2
    assert 0 <= c["grid_x"] <= 24 - 2
    assert 0 <= c["grid_y"] <= 16 - 2

    bed = _container("Grid Bed 1", kind="raised bed", year=2035, size="4x8 ft")
    assert (bed["grid_w"], bed["grid_h"]) == (4, 8)

    pot = _container("Grid Pot 1", kind="pot", year=2035)
    assert (pot["grid_w"], pot["grid_h"]) == (1, 1)

    arch = _container("Bean Arch", kind="arch", year=2035)
    assert (arch["grid_w"], arch["grid_h"]) == (4, 8)

    pallet = _container("Pallet Bin", kind="pallet", year=2035)
    assert (pallet["grid_w"], pallet["grid_h"]) == (4, 3)


def test_new_containers_do_not_overlap():
    a = _container("NoOverlap A", year=2035)
    b = _container("NoOverlap B", year=2035)

    def rect(c):
        return (c["grid_x"], c["grid_y"], c["grid_w"], c["grid_h"])

    ra, rb = rect(a), rect(b)
    overlap = (ra[0] < rb[0] + rb[2] and rb[0] < ra[0] + ra[2]
               and ra[1] < rb[1] + rb[3] and rb[1] < ra[1] + ra[3])
    assert not overlap


def test_patch_grid_position_clamped():
    c = _container("Clamp Bag", year=2035)
    r = client.patch(f"/api/containers/{c['id']}", json={"grid_x": -5, "grid_y": 3})
    assert r.status_code == 200
    assert r.json()["grid_x"] == 0
    r = client.patch(f"/api/containers/{c['id']}", json={"grid_w": 0})
    assert r.json()["grid_w"] == 1


def test_legacy_xy_backfilled_to_grid():
    # Simulate a pre-2.15 container row: insert with NULL grid cols via raw SQL-ish path.
    from app.database import get_session
    from app.models import Container
    session = next(get_session())
    legacy = Container(name="Legacy Bag", kind="grow bag", season_year=2035,
                       x=50.0, y=25.0, grid_x=None, grid_y=None, grid_w=None, grid_h=None)
    session.add(legacy)
    session.commit()
    lid = legacy.id
    session.close()

    r = client.get("/api/containers/?year=2035")
    assert r.status_code == 200
    found = [c for c in r.json() if c["id"] == lid][0]
    assert found["grid_x"] == 12  # 50% of 24 cols
    assert found["grid_y"] == 4   # 25% of 16 rows
    assert (found["grid_w"], found["grid_h"]) == (2, 2)


# --------------------------------------------------------------------------- #
# Multi-plant containers
# --------------------------------------------------------------------------- #
def test_plantings_crud_and_dedupe():
    hab = _plant("Grid Hab")
    fat = _plant("Grid Fatalii")
    c = _container("Multi Bag", year=2035)

    r = client.post("/api/containers/plantings",
                    json={"container_id": c["id"], "plant_id": hab["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["variety_name"] == "Grid Hab"
    pid = r.json()["id"]

    # same plant twice -> 409
    r = client.post("/api/containers/plantings",
                    json={"container_id": c["id"], "plant_id": hab["id"]})
    assert r.status_code == 409

    r = client.post("/api/containers/plantings",
                    json={"container_id": c["id"], "plant_id": fat["id"]})
    assert r.status_code == 201

    r = client.get("/api/containers/plantings?year=2035")
    mine = [p for p in r.json() if p["container_id"] == c["id"]]
    assert len(mine) == 2

    r = client.delete(f"/api/containers/plantings/{pid}")
    assert r.status_code == 204
    r = client.get("/api/containers/plantings?year=2035")
    assert len([p for p in r.json() if p["container_id"] == c["id"]]) == 1


def test_legacy_plant_id_backfilled_to_plantings():
    p = _plant("Legacy Plant")
    c = _container("Legacy Plant Bag", year=2035, plant_id=p["id"])
    r = client.get("/api/containers/plantings?year=2035")
    mine = [x for x in r.json() if x["container_id"] == c["id"]]
    assert len(mine) == 1 and mine[0]["plant_id"] == p["id"]

    # second read must not duplicate
    client.get("/api/containers/?year=2035")
    r = client.get("/api/containers/plantings?year=2035")
    assert len([x for x in r.json() if x["container_id"] == c["id"]]) == 1


def test_delete_container_removes_plantings():
    p = _plant("Doomed Plant")
    c = _container("Doomed Bag", year=2035)
    client.post("/api/containers/plantings",
                json={"container_id": c["id"], "plant_id": p["id"]})
    r = client.delete(f"/api/containers/{c['id']}")
    assert r.status_code == 204
    r = client.get("/api/containers/plantings?year=2035")
    assert not [x for x in r.json() if x["container_id"] == c["id"]]


def test_copy_season_copies_grid_and_plantings():
    p = _plant("Copy Plant")
    src = _container("Copy Bag", kind="raised bed", year=2034, size="4x4 ft")
    client.patch(f"/api/containers/{src['id']}", json={"grid_x": 5, "grid_y": 6})
    client.post("/api/containers/plantings",
                json={"container_id": src["id"], "plant_id": p["id"]})

    r = client.post("/api/containers/copy-season",
                    json={"from_year": 2034, "to_year": 2036})
    assert r.status_code == 200, r.text
    copied = [c for c in r.json() if c["name"] == "Copy Bag"][0]
    assert (copied["grid_x"], copied["grid_y"]) == (5, 6)
    assert (copied["grid_w"], copied["grid_h"]) == (4, 4)

    r = client.get("/api/containers/plantings?year=2036")
    mine = [x for x in r.json() if x["container_id"] == copied["id"]]
    assert len(mine) == 1 and mine[0]["variety_name"] == "Copy Plant"


# --------------------------------------------------------------------------- #
# Rotation warnings
# --------------------------------------------------------------------------- #
def test_rotation_warnings_same_family():
    # 2034: pepper in "Rotation Bag"; 2035: another pepper in "Rotation Bag"
    old = _plant("Rot Old Pepper")
    new = _plant("Rot New Pepper")
    c25 = _container("Rotation Bag", year=2034)
    c26 = _container("Rotation Bag", year=2035)
    client.post("/api/containers/plantings",
                json={"container_id": c25["id"], "plant_id": old["id"]})
    client.post("/api/containers/plantings",
                json={"container_id": c26["id"], "plant_id": new["id"]})

    r = client.get("/api/containers/rotation-warnings?year=2035")
    assert r.status_code == 200, r.text
    mine = [w for w in r.json() if w["container_id"] == c26["id"]]
    assert len(mine) == 1
    assert mine[0]["prev_year"] == 2034
    assert "2034" in mine[0]["reason"]


def test_rotation_no_warning_different_family():
    tomato = _plant("Rot Tomato", species="Solanum lycopersicum", family="Solanaceae")
    basil = _plant("Rot Basil", species="Ocimum basilicum", family="Lamiaceae")
    c25 = _container("Rotation Bag 2", year=2034)
    c26 = _container("Rotation Bag 2", year=2035)
    client.post("/api/containers/plantings",
                json={"container_id": c25["id"], "plant_id": tomato["id"]})
    client.post("/api/containers/plantings",
                json={"container_id": c26["id"], "plant_id": basil["id"]})

    r = client.get("/api/containers/rotation-warnings?year=2035")
    mine = [w for w in r.json() if w["container_id"] == c26["id"]]
    assert mine == []


def test_rotation_falls_back_to_species_type():
    # No family_genus recorded: same species_type still warns.
    a = _plant("Rot Pepper A", family=None)
    b = _plant("Rot Pepper B", family=None)
    c25 = _container("Rotation Bag 3", year=2034)
    c26 = _container("Rotation Bag 3", year=2035)
    client.post("/api/containers/plantings",
                json={"container_id": c25["id"], "plant_id": a["id"]})
    client.post("/api/containers/plantings",
                json={"container_id": c26["id"], "plant_id": b["id"]})

    r = client.get("/api/containers/rotation-warnings?year=2035")
    mine = [w for w in r.json() if w["container_id"] == c26["id"]]
    assert len(mine) == 1
