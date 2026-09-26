"""v2.13.0 tests: measurement cleanup — weight units, amount parsing, yield split,
temperature setting, container volumes, seed counts.

Run with:  pytest -q      (shares the same temp DB as the other test modules)
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="v213-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app import units as units_mod  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.import_csv import _parse_amount  # noqa: E402

TODAY = date.today()
YEAR = TODAY.year


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def _csv(text: str):
    return {"file": ("data.csv", io.BytesIO(text.encode("utf-8-sig")), "text/csv")}


def _run(client, entity, text, assignments=None):
    data = {"entity": entity, "assignments": json.dumps(assignments or {})}
    res = client.post("/api/import/run", data=data, files=_csv(text))
    assert res.status_code == 200, res.text
    return res.json()


def _make_plant(client, name):
    res = client.post("/api/plants/", json={"variety_name": name, "species_type": "Pepper"})
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# units module
# --------------------------------------------------------------------------- #
def test_to_oz_conversions():
    assert units_mod.to_oz(16, "oz") == 16.0
    assert units_mod.to_oz(1, "lb") == 16.0
    assert units_mod.to_oz(1, "lbs") == 16.0
    assert units_mod.to_oz(1000, "g") == pytest.approx(35.274)
    assert units_mod.to_oz(1, "kg") == pytest.approx(35.274)
    assert units_mod.to_oz(2, "Ounces") == 2.0  # case-insensitive, plural ok
    assert units_mod.to_oz(None, "oz") is None
    assert units_mod.to_oz(5, "fruit") is None  # not a weight unit
    assert units_mod.to_oz(5, "") is None


def test_normalize_weight_unit():
    assert units_mod.normalize_weight_unit("Ounces") == "oz"
    assert units_mod.normalize_weight_unit("LBS") == "lb"
    assert units_mod.normalize_weight_unit("grams") == "g"
    assert units_mod.normalize_weight_unit("") == "oz"
    assert units_mod.normalize_weight_unit(None) == "oz"
    assert units_mod.normalize_weight_unit("furlongs") == "oz"  # unknown -> default


def test_parse_amount():
    assert _parse_amount("2 gal") == (2.0, "gal")
    assert _parse_amount("1.5tbsp") == (1.5, "tbsp")
    assert _parse_amount("500 ml") == (500.0, "ml")
    assert _parse_amount("a good soak") == (None, "")
    assert _parse_amount("2 furlongs") == (None, "")
    assert _parse_amount("") == (None, "")
    assert _parse_amount(None) == (None, "")


# --------------------------------------------------------------------------- #
# Harvest weight units
# --------------------------------------------------------------------------- #
def test_harvest_weight_unit_round_trip(client):
    p = _make_plant(client, "Unit Tester")
    res = client.post("/api/harvests/", json={
        "plant_id": p["id"], "date": date(YEAR, 7, 10).isoformat(),
        "quantity": 12, "unit": "fruit", "weight": 500, "weight_unit": "grams",
        "notes": "",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["weight"] == 500
    assert body["weight_unit"] == "g"  # normalized spelling

    # legacy default: no unit given -> oz
    res = client.post("/api/harvests/", json={
        "plant_id": p["id"], "date": date(YEAR, 7, 11).isoformat(),
        "quantity": 3, "unit": "fruit", "weight": 9, "notes": "",
    })
    assert res.json()["weight_unit"] == "oz"


def test_harvest_weight_unit_normalized_on_patch(client):
    p = _make_plant(client, "Patch Tester")
    res = client.post("/api/harvests/", json={
        "plant_id": p["id"], "date": date(YEAR, 7, 12).isoformat(),
        "quantity": 5, "unit": "fruit", "weight": 8, "weight_unit": "oz", "notes": "",
    })
    hid = res.json()["id"]
    res = client.patch(f"/api/harvests/{hid}", json={"weight_unit": "Pounds"})
    assert res.status_code == 200, res.text
    assert res.json()["weight_unit"] == "lb"


def test_import_harvest_weight_and_backfill(client):
    p = _make_plant(client, "Backfill Pepper")
    csv_text = (
        "id,Log ID,Date,Quantity,Unit,Weight,Weight Unit,Notes\n"
        f"1,H-213-001,07/15/{YEAR},20,fruit,12,oz,first import\n"
    )
    # plant assignment needed: use variety-name hint via direct harvest_id flow —
    # simpler to import then check; needs_plant would trigger without assignment,
    # so pass the assignment explicitly.
    out = _run(client, "harvests", csv_text, assignments={"H-213-001": p["id"]})
    assert out["imported"] == 1, out

    res = client.get("/api/harvests/", params={"plant_id": p["id"]})
    rows = [h for h in res.json() if h["harvest_id"] == "H-213-001"]
    assert rows and rows[0]["weight"] == 12
    assert rows[0]["weight_unit"] == "oz"

    # Re-import the same file without the weight column: skips, no backfill.
    csv_text2 = (
        "id,Log ID,Date,Quantity,Unit,Notes\n"
        f"1,H-213-001,07/15/{YEAR},20,fruit,second pass\n"
    )
    out = _run(client, "harvests", csv_text2, assignments={"H-213-001": p["id"]})
    assert out["skipped"] == 1 and out["updated"] == 0, out


def test_import_harvest_backfills_missing_weight(client):
    p = _make_plant(client, "Weightless Pepper")
    # First import: no weight columns at all (like Josh's real 2026 import).
    csv_text = (
        "id,Log ID,Date,Quantity,Unit,Notes\n"
        f"1,H-213-002,07/16/{YEAR},15,fruit,no weight yet\n"
    )
    out = _run(client, "harvests", csv_text, assignments={"H-213-002": p["id"]})
    assert out["imported"] == 1, out

    # Second import WITH weights: backfills the existing row instead of skipping.
    csv_text2 = (
        "id,Log ID,Date,Quantity,Unit,Weight,Weight Unit,Notes\n"
        f"1,H-213-002,07/16/{YEAR},15,fruit,10.5,oz,now with weight\n"
    )
    out = _run(client, "harvests", csv_text2, assignments={"H-213-002": p["id"]})
    assert out["updated"] == 1, out
    assert out["imported"] == 0

    res = client.get("/api/harvests/", params={"plant_id": p["id"]})
    rows = [h for h in res.json() if h["harvest_id"] == "H-213-002"]
    assert rows and rows[0]["weight"] == 10.5
    assert rows[0]["weight_unit"] == "oz"


def test_import_parses_amounts(client):
    csv_text = (
        "id,Log ID,Location,Link to Plant,Date,Method,Amount,Notes\n"
        f"1,W-213-001,,,{TODAY.strftime('%m/%d/%Y')},Hose,2 gal,parsed\n"
        f"2,W-213-002,,,{TODAY.strftime('%m/%d/%Y')},Can,a good soak,unparsed\n"
    )
    # watering import needs a location; create one first
    loc = client.post("/api/locations/", params={"name": "Amount Test Bed", "type": "Raised Bed"})
    assert loc.status_code == 201, loc.text
    csv_text = csv_text.replace("W-213-001,,,", f"W-213-001,{loc.json()['location_id']},,")
    csv_text = csv_text.replace("W-213-002,,,", f"W-213-002,{loc.json()['location_id']},,")
    out = _run(client, "watering", csv_text)
    assert out["imported"] == 2, out
    res = client.get("/api/watering-logs/", params={"location_id": loc.json()["id"]})
    rows = {w["watering_id"]: w for w in res.json()}
    assert rows["W-213-001"]["amount_value"] == 2.0
    assert rows["W-213-001"]["amount_unit"] == "gal"
    assert rows["W-213-001"]["amount"] == "2 gal"  # raw text preserved
    assert rows["W-213-002"]["amount_value"] is None
    assert rows["W-213-002"]["amount"] == "a good soak"


# --------------------------------------------------------------------------- #
# Temperature setting
# --------------------------------------------------------------------------- #
def test_temperature_unit_setting(client):
    res = client.get("/api/settings")
    assert res.status_code == 200
    assert res.json()["temperature_unit"] == "F"  # default

    res = client.put("/api/settings", json={
        "zone": "", "frost_date": "", "last_frost_date": "",
        "digest_enabled": False, "discord_webhook_url": "",
        "digest_time": "08:00", "temperature_unit": "C",
    })
    assert res.status_code == 200, res.text
    assert res.json()["temperature_unit"] == "C"

    res = client.put("/api/settings", json={
        "zone": "", "frost_date": "", "last_frost_date": "",
        "digest_enabled": False, "discord_webhook_url": "",
        "digest_time": "08:00", "temperature_unit": "Kelvin",
    })
    assert res.status_code == 400

    # restore default for other tests / the shared DB
    client.put("/api/settings", json={
        "zone": "", "frost_date": "", "last_frost_date": "",
        "digest_enabled": False, "discord_webhook_url": "",
        "digest_time": "08:00", "temperature_unit": "F",
    })


# --------------------------------------------------------------------------- #
# Containers + seed packets
# --------------------------------------------------------------------------- #
def test_container_volume(client):
    res = client.post("/api/containers/", json={
        "name": "Vol Bag", "kind": "grow bag",
        "volume_value": 10, "volume_unit": "gal",
        "season_year": YEAR,
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["volume_value"] == 10
    assert body["volume_unit"] == "gal"

    res = client.patch(f"/api/containers/{body['id']}", json={"volume_unit": "L"})
    assert res.status_code == 200
    assert res.json()["volume_unit"] == "L"


def test_seed_packet_seed_count(client):
    res = client.post("/api/seed-packets/", json={
        "variety_name": "Counted Pepper", "quantity": "~40 seeds", "seed_count": 38,
    })
    assert res.status_code == 201, res.text
    assert res.json()["seed_count"] == 38
    pid = res.json()["id"]
    res = client.patch(f"/api/seed-packets/{pid}", json={"seed_count": 35})
    assert res.status_code == 200
    assert res.json()["seed_count"] == 35


def test_watering_structured_amount_api(client):
    loc = client.post("/api/locations/", params={"name": "API Amount Bed"})
    assert loc.status_code == 201
    res = client.post("/api/watering-logs/", json={
        "location_id": loc.json()["id"], "date": TODAY.isoformat(),
        "method": "Hose", "amount": "2 gal", "amount_value": 2, "amount_unit": "gal",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["amount_value"] == 2
    assert body["amount_unit"] == "gal"
