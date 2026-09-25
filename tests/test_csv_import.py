"""CSV import tests: preview/run endpoints, idempotency, link resolution.

Run with:  pytest -q      (shares the same temp DB as test_api.py)
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="csvimport-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def _csv(text: str):
    return {"file": ("data.csv", io.BytesIO(text.encode("utf-8-sig")), "text/csv")}


def _preview(client, entity, text):
    res = client.post("/api/import/preview", data={"entity": entity}, files=_csv(text))
    assert res.status_code == 200, res.text
    return res.json()


def _run(client, entity, text, assignments=None):
    data = {"entity": entity, "assignments": json.dumps(assignments or {})}
    res = client.post("/api/import/run", data=data, files=_csv(text))
    assert res.status_code == 200, res.text
    return res.json()


LOCATIONS_CSV = """id,Location ID,Name,Type,Light,Notes,Plants,Watering Logs
1,LOC-IMP-01,Imp Tomato,Container,Full Sun,imported,,
2,LOC-IMP-02,Imp Herbs,Raised Bed,Partial Shade,,,
"""

PLANTS_CSV = """id,Plant ID,Variety Name,Species / Type,Family / Genus,Category,Status,Location,Date Planted,Date Started Indoors,Days to Maturity,Light,Notes
1,PL-IMP-01,Imp Sungold,Tomato,Solanaceae,Annual,Growing,LOC-IMP-01,04/15/2026,03/01/2026,65,Full Sun,imported plant
2,PL-IMP-02,Imp Habanero,Pepper,Solanaceae,Annual,Growing,LOC-IMP-02,,,,Full Sun,
"""

FERTILIZERS_CSV = """id,Fertilizer ID,Name,N-P-K,Best For,Notes
1,FERT-IMP-01,Imp Feed,4-6-3,All-Purpose,imported
"""

SEED_SOURCES_CSV = """id,Source ID,Source Name,Source Type,Contact / URL,Year Acquired,Seed Harvest Year,Link To Plant,Notes
1,SRC-IMP-01,Imp Vendor,Vendor,https://example.com/seeds,2026,,,imported source
2,SRC-IMP-02,Imp Trader,Seed Trade,,2025,,PL-IMP-02,
"""

FERT_LOGS_CSV = """id,Log ID,Link to Plant,Fertilizer,Date,Year / Season,Amount / Concentration,Application,Notes
1,FE-IMP-001,PL-IMP-01,FERT-IMP-01,08/09/2026,2026,1 tbsp,Liquid,
2,FE-IMP-002,,FERT-IMP-01,08/10/2026,2026,,Granular,no plant linked
"""

HARVESTS_CSV = """id,Log ID,Link to Plant,Date,Year / Season,Quantity,Unit,Notes
1,H-IMP-001,,08/19/2026,2026,19,,19 fruit (count)
2,H-IMP-002,,08/19/2026,2026,5,,5 fruit (count)
"""


def test_import_page_renders(client):
    res = client.get("/import")
    assert res.status_code == 200
    assert 'id="panel-import"' in res.text


def test_nav_import_on_every_page(client):
    for page in ["/", "/observations", "/calendar", "/photos", "/plants", "/seeds", "/review", "/backup", "/import"]:
        res = client.get(page)
        assert res.status_code == 200, page
        assert 'href="/import"' in res.text, f"missing Import nav on {page}"


def test_preview_and_run_locations_idempotent(client):
    prev = _preview(client, "locations", LOCATIONS_CSV)
    assert prev["total_rows"] == 2
    assert prev["counts"]["new"] == 2

    first = _run(client, "locations", LOCATIONS_CSV)
    assert first["imported"] == 2 and first["skipped"] == 0 and not first["errors"]

    second = _run(client, "locations", LOCATIONS_CSV)
    assert second["imported"] == 0 and second["skipped"] == 2

    locs = client.get("/api/locations/").json()
    imp = [l for l in locs if l["location_id"] in ("LOC-IMP-01", "LOC-IMP-02")]
    assert len(imp) == 2
    assert {l["name"] for l in imp} == {"Imp Tomato", "Imp Herbs"}


def test_plants_import_with_dates_and_location_link(client):
    res = _run(client, "plants", PLANTS_CSV)
    assert res["imported"] == 2, res["errors"]
    plants = client.get("/api/plants/").json()
    sungold = next(p for p in plants if p["plant_id"] == "PL-IMP-01")
    assert sungold["variety_name"] == "Imp Sungold"
    assert sungold["date_planted"] == "2026-04-15"
    assert sungold["date_started_indoors"] == "2026-03-01"
    assert sungold["days_to_maturity"] == 65
    locs = {l["id"]: l for l in client.get("/api/locations/").json()}
    assert locs[sungold["location_id"]]["location_id"] == "LOC-IMP-01"


def test_fertilizers_and_seed_sources(client):
    res = _run(client, "fertilizers", FERTILIZERS_CSV)
    assert res["imported"] == 1, res["errors"]

    res = _run(client, "seed_sources", SEED_SOURCES_CSV)
    assert res["imported"] == 2, res["errors"]
    sources = client.get("/api/seed-sources/").json()
    vendor = next(s for s in sources if s["source_id"] == "SRC-IMP-01")
    assert vendor["variety"] == ""  # variety is optional since v2.5.0
    assert "https://example.com/seeds" in (vendor["notes"] or "")
    assert "Acquired: 2026" in (vendor["notes"] or "")
    trader = next(s for s in sources if s["source_id"] == "SRC-IMP-02")
    assert trader["variety"] == "Imp Habanero"  # backfilled from the linked plant
    assert trader["linked_plant_id"] is not None


def test_seed_source_api_accepts_missing_variety(client):
    res = client.post("/api/seed-sources/", json={
        "source_id": "SRC-IMP-03",
        "source": "Imp Vendor 3",
        "type": "Vendor Purchase",
    })
    assert res.status_code == 201, res.text
    assert res.json()["variety"] == ""


def test_fertilization_logs_plantless_and_idempotent(client):
    res = _run(client, "fertilization", FERT_LOGS_CSV)
    assert res["imported"] == 2, res["errors"]
    logs = client.get("/api/fertilizations/").json()
    imp = [l for l in logs if l["date"] in ("2026-08-09", "2026-08-10") and "Imp Feed" in l["fertilizer_name"]]
    assert len(imp) == 2
    plantless = next(l for l in imp if l["date"] == "2026-08-10")
    assert plantless["plant_id"] is None
    assert "Granular" in (plantless["notes"] or "")

    again = _run(client, "fertilization", FERT_LOGS_CSV)
    assert again["imported"] == 0 and again["skipped"] == 2


def test_harvests_need_plant_then_import_with_assignment(client):
    prev = _preview(client, "harvests", HARVESTS_CSV)
    assert prev["counts"]["needs_plant"] == 2
    assert len(prev["assign_rows"]) == 2
    assert prev["needs_plants_first"] is False

    # Import with no assignments: nothing importable, rows reported as errors.
    res = _run(client, "harvests", HARVESTS_CSV)
    assert res["imported"] == 0
    assert len(res["errors"]) == 2

    plants = {p["plant_id"]: p["id"] for p in client.get("/api/plants/").json()}
    res = _run(client, "harvests", HARVESTS_CSV, assignments={
        "H-IMP-001": plants["PL-IMP-01"],
        "H-IMP-002": plants["PL-IMP-02"],
    })
    assert res["imported"] == 2, res["errors"]
    harvests = client.get("/api/harvests/").json()
    h1 = next(h for h in harvests if h["harvest_id"] == "H-IMP-001")
    assert h1["quantity"] == 19 and h1["plant_id"] == plants["PL-IMP-01"]

    # Idempotent on the natural key too.
    again = _run(client, "harvests", HARVESTS_CSV, assignments={
        "H-IMP-001": plants["PL-IMP-01"],
        "H-IMP-002": plants["PL-IMP-02"],
    })
    assert again["imported"] == 0 and again["skipped"] == 2


def test_preview_unknown_entity_rejected(client):
    res = client.post("/api/import/preview", data={"entity": "nope"}, files=_csv("a,b\n1,2\n"))
    assert res.status_code == 400
