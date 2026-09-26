"""v2.10.0: fertilizers UI API, seed catalog, NFC tags, containers/planner, scorecard."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="garden-v210-"))
os.environ["GARDEN_DATA_DIR"] = str(TMP / "data")
os.environ["GARDEN_UPLOAD_DIR"] = str(TMP / "uploads")
os.environ["GARDEN_DATABASE_URL"] = f"sqlite:///{TMP / 'data' / 'garden.db'}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _plant(variety="Habanero"):
    r = client.post("/api/plants/", json={"variety_name": variety, "species_type": "Capsicum chinense"})
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Fertilizers (JSON body create, deterministic-ish IDs)
# --------------------------------------------------------------------------- #
def test_fertilizer_crud_json():
    r = client.post("/api/fertilizers/", json={"name": "Fish emulsion", "npk_ratio": "5-1-1"})
    assert r.status_code == 201, r.text
    fert = r.json()
    assert fert["fertilizer_id"].startswith("FERT-")

    r = client.post("/api/fertilizers/", json={"name": "Fish emulsion"})
    assert r.status_code == 409  # duplicate name rejected

    r = client.get("/api/fertilizers/")
    assert any(f["name"] == "Fish emulsion" for f in r.json())

    r = client.patch(f"/api/fertilizers/{fert['id']}", json={"best_for": "peppers"})
    assert r.status_code == 200 and r.json()["best_for"] == "peppers"

    r = client.delete(f"/api/fertilizers/{fert['id']}")
    assert r.status_code == 204


# --------------------------------------------------------------------------- #
# Seed packets
# --------------------------------------------------------------------------- #
def test_seed_packet_crud():
    r = client.post("/api/seed-packets/", json={"variety_name": "Fatalii"})
    assert r.status_code == 201, r.text
    packet = r.json()
    assert packet["packet_id"].startswith("SEEDPK-")

    r = client.post("/api/seed-packets/", json={"variety_name": " "})
    assert r.status_code == 422

    r = client.post(
        "/api/seed-packets/",
        json={
            "variety_name": "Aji Pineapple",
            "species_type": "Capsicum baccatum",
            "category": "Pepper",
            "vendor_url": "https://example.com/aji",
            "year_acquired": 2025,
            "quantity": "~30 seeds",
        },
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = client.get("/api/seed-packets/", params={"q": "aji"})
    assert len(r.json()) == 1
    r = client.get("/api/seed-packets/", params={"category": "Pepper"})
    assert len(r.json()) == 1

    r = client.patch(f"/api/seed-packets/{pid}", json={"quantity": "~25 seeds"})
    assert r.json()["quantity"] == "~25 seeds"

    # photo upload
    png = (
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    )
    r = client.post(
        f"/api/seed-packets/{pid}/photo",
        files={"file": ("packet.png", png, "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["photo_path"].startswith("/uploads/")

    r = client.delete(f"/api/seed-packets/{pid}")
    assert r.status_code == 204
    r = client.get(f"/api/seed-packets/{packet['id']}")
    assert r.status_code == 200
    client.delete(f"/api/seed-packets/{packet['id']}")


# --------------------------------------------------------------------------- #
# NFC tags + /t/ redirect
# --------------------------------------------------------------------------- #
def test_tag_crud_and_tap():
    plant = _plant("Scotch Bonnet")

    r = client.post("/api/tags/", json={"label": "nope"})
    assert r.status_code == 422  # missing action
    r = client.post("/api/tags/", json={"label": "x", "action": "bogus"})
    assert r.status_code == 422  # unknown action

    r = client.post(
        "/api/tags/",
        json={"label": "Scotch Bonnet bag", "action": "plant", "target_id": plant["id"]},
    )
    assert r.status_code == 201, r.text
    tag = r.json()
    assert len(tag["code"]) >= 6

    r = client.get(f"/t/{tag['code']}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == f"/plants?plant={plant['id']}"

    # tap counted
    r = client.get(f"/api/tags/{tag['id']}")
    assert r.json()["tap_count"] == 1

    r = client.get("/t/definitely-not-a-code", follow_redirects=False)
    assert r.status_code == 404

    r = client.patch(f"/api/tags/{tag['id']}", json={"label": "Renamed"})
    assert r.json()["label"] == "Renamed"
    r = client.patch(f"/api/tags/{tag['id']}", json={"action": "bogus"})
    assert r.status_code == 422

    r = client.delete(f"/api/tags/{tag['id']}")
    assert r.status_code == 204


def test_tag_destinations():
    from app.routers.tags import tag_destination

    cases = [
        ({"action": "fertilize", "target_id": 7, "target_text": ""}, "/observations?fertilizer=7"),
        ({"action": "pest", "target_id": None, "target_text": "Neem oil"}, "/pests?product=Neem oil"),
        ({"action": "harvest_any", "target_id": None, "target_text": ""}, "/quick?action=harvest"),
        ({"action": "seed_add", "target_id": None, "target_text": ""}, "/seeds?tab=catalog&add=1"),
        ({"action": "location", "target_id": 3, "target_text": ""}, "/quick?location=3"),
        ({"action": "water", "target_id": 3, "target_text": ""}, "/quick?action=water&location=3"),
    ]
    for kwargs, expected in cases:
        assert tag_destination(type("T", (), kwargs)()) == expected


# --------------------------------------------------------------------------- #
# Containers / planner
# --------------------------------------------------------------------------- #
def test_container_crud_and_copy_season():
    r = client.post("/api/containers/", json={"name": " "})
    assert r.status_code == 422
    r = client.post(
        "/api/containers/",
        json={"name": "Grow bag 1", "kind": "grow bag", "size": "10 gal", "season_year": 2026, "x": 20, "y": 30},
    )
    assert r.status_code == 201, r.text
    c1 = r.json()

    r = client.get("/api/containers/", params={"year": 2026})
    assert len(r.json()) == 1
    r = client.get("/api/containers/", params={"year": 2027})
    assert r.json() == []

    r = client.patch(f"/api/containers/{c1['id']}", json={"x": 42.5, "plant_id": None})
    assert r.json()["x"] == 42.5

    # copy season
    r = client.post("/api/containers/copy-season", json={"from_year": 2026, "to_year": 2027})
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1 and r.json()[0]["season_year"] == 2027
    r = client.post("/api/containers/copy-season", json={"from_year": 2026, "to_year": 2027})
    assert r.status_code == 409  # target season already populated

    r = client.get("/api/containers/years")
    assert 2026 in r.json() and 2027 in r.json()

    r = client.delete(f"/api/containers/{c1['id']}")
    assert r.status_code == 204


# --------------------------------------------------------------------------- #
# Scorecard + expense plant linkage
# --------------------------------------------------------------------------- #
def test_scorecard():
    p1 = _plant("Score Pepper A")
    p2 = _plant("Score Pepper B")
    client.post("/api/harvests/", json={"plant_id": p1["id"], "date": "2026-08-01", "quantity": 10, "weight": 8.0})
    client.post("/api/harvests/", json={"plant_id": p1["id"], "date": "2026-08-15", "quantity": 5, "weight": 4.0})
    client.post("/api/harvests/", json={"plant_id": p2["id"], "date": "2026-08-10", "quantity": 2})
    client.post(
        "/api/expenses/",
        json={"date": "2026-05-01", "category": "Soil", "description": "Potting mix", "amount": 12.0, "plant_id": p1["id"]},
    )
    client.post(
        "/api/expenses/",
        json={"date": "2026-05-02", "category": "Tools", "description": "Trowel", "amount": 9.0},
    )

    r = client.get("/api/stats/scorecard", params={"year": 2026})
    assert r.status_code == 200, r.text
    data = r.json()
    by_var = {v["variety"]: v for v in data["varieties"]}
    a = by_var["Score Pepper A"]
    assert a["total_qty"] == 15 and a["total_oz"] == 12.0 and a["harvest_events"] == 2
    assert a["direct_cost"] == 12.0 and a["cost_per_oz"] == 1.0
    b = by_var["Score Pepper B"]
    assert b["total_qty"] == 2 and b["cost_per_oz"] is None
    assert data["total_spent"] >= 21.0
    assert data["unassigned_spent"] >= 9.0
    # ranked by ounces (A above B; other test files' varieties may also rank)
    order = [v["variety"] for v in data["varieties"]]
    assert order.index("Score Pepper A") < order.index("Score Pepper B")


def test_upgrade_adds_new_columns(tmp_path=None):
    """Old DBs gain expenses.plant_id via the automatic column sync."""
    import sqlite3

    db_path = TMP / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE expenses (id INTEGER PRIMARY KEY, date TEXT, category TEXT, description TEXT, amount REAL, notes TEXT)")
    conn.commit()
    conn.close()

    from sqlalchemy import create_engine

    from app.database import _apply_column_migrations

    eng = create_engine(f"sqlite:///{db_path}")
    _apply_column_migrations(eng)
    cols = [r[1] for r in eng.connect().exec_driver_sql("PRAGMA table_info(expenses)").fetchall()]
    assert "plant_id" in cols


# --------------------------------------------------------------------------- #
# Seed stash fixes: vendor as plain text, move-sources-to-stash, backfill
# --------------------------------------------------------------------------- #
def test_packet_vendor_name_and_vendors_endpoint():
    r = client.post(
        "/api/seed-packets/",
        json={"variety_name": "VendorTest Pepper", "vendor_name": "Territorial Seed",
              "vendor_url": "territorialseed.com"},
    )
    assert r.status_code == 201, r.text
    packet = r.json()
    assert packet["vendor_name"] == "Territorial Seed"
    # scheme-less URLs get normalized so the card link works
    assert packet["vendor_url"] == "https://territorialseed.com"

    r = client.post(
        "/api/seed-packets/",
        json={"variety_name": "VendorTest Tomato", "vendor_name": "Territorial Seed"},
    )
    assert r.status_code == 201

    r = client.get("/api/seed-packets/vendors")
    assert r.status_code == 200, r.text
    vendors = r.json()
    # each vendor exactly once, no matter how many packets use it
    assert vendors.count("Territorial Seed") == 1


def test_from_sources_conversion():
    from app.models import SeedSource

    def add_source(code, source, variety, notes):
        r = client.post(
            "/api/seed-sources/",
            json={"source_id": code, "source": source, "variety": variety, "notes": notes},
        )
        assert r.status_code == 201, r.text

    add_source("SRC-T1", "Baker Creek", "Aji Pineapple",
               "URL: rareseeds.com\nAcquired: 2025\nGreat germination.")
    add_source("SRC-T2", "Baker Creek", "Sungold",
               "URL: https://rareseeds.com\nAcquired: 2026")
    add_source("SRC-T3", "Seed Savers", "",
               "Just the vendor, no variety recorded.")

    r = client.post("/api/seed-packets/from-sources")
    assert r.status_code == 201, r.text
    result = r.json()
    # NB: shared test DB — other test files import seed sources too
    assert result["created"] >= 3, result

    r = client.get("/api/seed-packets/", params={"q": "Aji Pineapple"})
    packets = [p for p in r.json() if p["vendor_name"] == "Baker Creek"]
    assert len(packets) == 1
    aji = packets[0]
    assert aji["vendor_url"] == "https://rareseeds.com"
    assert aji["year_acquired"] == 2025
    assert "Great germination." in (aji["notes"] or "")
    assert "URL:" not in (aji["notes"] or "")  # folded lines were extracted

    r = client.get("/api/seed-packets/", params={"q": "Unknown variety"})
    unknowns = [p for p in r.json() if p["vendor_name"] == "Seed Savers"]
    assert len(unknowns) == 1

    # idempotent: re-running moves nothing new (my 3 sources all skipped now)
    before = client.post("/api/seed-packets/from-sources").json()
    after = client.post("/api/seed-packets/from-sources").json()
    assert after["created"] == 0
    assert after["skipped"] >= before["total"] >= 3


def test_packet_vendor_name_backfill():
    """Legacy packets (vendor_id -> seed_sources) get vendor_name on upgrade."""
    import sqlite3

    db_path = TMP / "legacy-packets.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE seed_sources (id INTEGER PRIMARY KEY, source_id TEXT, source TEXT, variety TEXT)")
    conn.execute("INSERT INTO seed_sources (id, source_id, source, variety) VALUES (1, 'SRC-1', 'Territorial Seed', 'Habanero')")
    conn.execute(
        "CREATE TABLE seed_packets (id INTEGER PRIMARY KEY, packet_id TEXT, variety_name TEXT, "
        "species_type TEXT, category TEXT, vendor_id INTEGER, vendor_url TEXT, year_acquired INTEGER, "
        "quantity TEXT, photo_path TEXT, notes TEXT, date_added TEXT)"
    )
    conn.execute(
        "INSERT INTO seed_packets (id, packet_id, variety_name, vendor_id) "
        "VALUES (1, 'SEEDPK-OLD', 'Habanero', 1)"
    )
    conn.commit()
    conn.close()

    from sqlalchemy import create_engine

    from app.database import _apply_column_migrations

    eng = create_engine(f"sqlite:///{db_path}")
    _apply_column_migrations(eng)
    name = eng.connect().exec_driver_sql(
        "SELECT vendor_name FROM seed_packets WHERE id = 1"
    ).fetchone()[0]
    assert name == "Territorial Seed"
