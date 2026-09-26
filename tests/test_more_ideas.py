"""v2.6.0 tests: slideshow page, yield leaderboard, quick-log APIs, costs, pests,
seed-starting calendar + digest hook.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="more-ideas-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.digest import build_digest_message  # noqa: E402
from app.schemas import SowRow  # noqa: E402

TODAY = date.today()
YEAR = TODAY.year


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def make_plant(client, name, **kwargs):
    payload = {"variety_name": name, "species_type": "Test species"}
    payload.update(kwargs)
    res = client.post("/api/plants/", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- #
def test_pages_return_200(client):
    for path in ("/slideshow", "/quick", "/costs", "/pests"):
        res = client.get(path)
        assert res.status_code == 200, f"{path}: {res.status_code}"


# --------------------------------------------------------------------------- #
def test_expenses_crud(client):
    res = client.post("/api/expenses/", json={
        "date": TODAY.isoformat(), "category": "Seeds",
        "description": "Pepper seeds", "amount": 12.50, "notes": "",
    })
    assert res.status_code == 201, res.text
    exp = res.json()
    assert exp["amount"] == 12.50
    assert exp["date"] == TODAY.isoformat()

    res = client.post("/api/expenses/", json={
        "date": TODAY.isoformat(), "category": "Soil",
        "description": "Potting mix", "amount": 8.0, "notes": "",
    })
    assert res.status_code == 201, res.text

    res = client.get("/api/expenses/", params={"category": "Seeds"})
    assert res.status_code == 200
    assert len(res.json()) == 1

    res = client.delete(f"/api/expenses/{exp['id']}")
    assert res.status_code == 204
    res = client.get("/api/expenses/", params={"category": "Seeds"})
    assert res.json() == []


def test_expense_rejects_negative(client):
    res = client.post("/api/expenses/", json={
        "date": TODAY.isoformat(), "category": "Seeds",
        "description": "x", "amount": -1, "notes": "",
    })
    assert res.status_code == 422


# --------------------------------------------------------------------------- #
def test_pests_crud_and_resolve(client):
    plant = make_plant(client, "Pest Test Pepper")
    res = client.post("/api/pests/", json={
        "date": TODAY.isoformat(), "pest_name": "Aphids",
        "plant_id": plant["id"], "treatment": "Neem oil", "notes": "",
    })
    assert res.status_code == 201, res.text
    log = res.json()
    assert log["resolved"] is False

    res = client.get("/api/pests/", params={"resolved": False})
    assert any(l["id"] == log["id"] for l in res.json())

    res = client.patch(f"/api/pests/{log['id']}", json={"resolved": True})
    assert res.status_code == 200
    assert res.json()["resolved"] is True

    res = client.get("/api/pests/", params={"resolved": True})
    assert any(l["id"] == log["id"] for l in res.json())

    res = client.delete(f"/api/pests/{log['id']}")
    assert res.status_code == 204


def test_pest_rejects_unknown_plant(client):
    res = client.post("/api/pests/", json={
        "date": TODAY.isoformat(), "pest_name": "Spider mites",
        "plant_id": 999999, "treatment": "", "notes": "",
    })
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
def test_yield_leaderboard(client):
    p1 = make_plant(client, "Yield Winner")
    p2 = make_plant(client, "Yield Runner Up")
    for i in range(5):
        res = client.post("/api/harvests/", json={
            "plant_id": p1["id"], "date": date(YEAR, 7, 1 + i).isoformat(),
            "quantity": 10, "unit": "fruit", "notes": "",
        })
        assert res.status_code == 201, res.text
    res = client.post("/api/harvests/", json={
        "plant_id": p2["id"], "date": date(YEAR, 7, 2).isoformat(),
        "quantity": 3, "unit": "fruit", "notes": "",
    })
    assert res.status_code == 201, res.text

    res = client.get("/api/stats/yield", params={"year": YEAR})
    assert res.status_code == 200
    board = res.json()
    # count leaderboard: same-unit sums only
    rows = {r["variety_name"]: r for r in board["by_count"]}
    assert rows["Yield Winner"]["total_quantity"] == 50
    assert rows["Yield Winner"]["harvest_count"] == 5
    assert rows["Yield Runner Up"]["total_quantity"] == 3
    # ranked: winner ahead of runner-up (other tests share this DB)
    order = [r["variety_name"] for r in board["by_count"]]
    assert order.index("Yield Winner") < order.index("Yield Runner Up")
    # no weighed harvests in this fixture
    assert "Yield Winner" not in {r["variety_name"] for r in board["by_weight"]}


def test_yield_leaderboard_splits_weight_and_count(client):
    p1 = make_plant(client, "Weigh Station")
    p2 = make_plant(client, "Counter Top")
    # 16 oz weighed harvest
    res = client.post("/api/harvests/", json={
        "plant_id": p1["id"], "date": date(YEAR, 7, 1).isoformat(),
        "quantity": 4, "unit": "fruit", "weight": 16, "weight_unit": "oz", "notes": "",
    })
    assert res.status_code == 201, res.text
    # 1 lb logged as quantity+unit (auto-derives weight)
    res = client.post("/api/harvests/", json={
        "plant_id": p1["id"], "date": date(YEAR, 7, 2).isoformat(),
        "quantity": 1, "unit": "lb", "notes": "",
    })
    assert res.status_code == 201, res.text
    assert res.json()["weight"] == 1.0
    assert res.json()["weight_unit"] == "lb"
    # pure count harvest
    res = client.post("/api/harvests/", json={
        "plant_id": p2["id"], "date": date(YEAR, 7, 3).isoformat(),
        "quantity": 7, "unit": "fruit", "notes": "",
    })
    assert res.status_code == 201, res.text

    res = client.get("/api/stats/yield", params={"year": YEAR})
    assert res.status_code == 200
    board = res.json()
    # by_weight: 16 oz + 1 lb (=16 oz) = 32 oz, never mixed with the fruit count
    wrows = {r["variety_name"]: r for r in board["by_weight"]}
    assert wrows["Weigh Station"]["total_oz"] == 32.0
    # by_count: only the piece-count harvest for this plant
    crows = {r["variety_name"]: r for r in board["by_count"]}
    assert crows["Counter Top"]["total_quantity"] == 7
    assert "Counter Top" not in wrows


def test_scorecard_converts_weight_units(client):
    p = make_plant(client, "Metric Pepper")
    res = client.post("/api/harvests/", json={
        "plant_id": p["id"], "date": date(YEAR, 8, 1).isoformat(),
        "quantity": 10, "unit": "fruit", "weight": 500, "weight_unit": "g", "notes": "",
    })
    assert res.status_code == 201, res.text
    res = client.get("/api/stats/scorecard", params={"year": YEAR})
    assert res.status_code == 200
    rows = {r["variety"]: r for r in res.json()["varieties"]}
    # 500 g = 17.6 oz
    assert rows["Metric Pepper"]["total_oz"] == round(500 * 0.035274, 1)


# --------------------------------------------------------------------------- #
def test_seed_calendar_pepper_offset(client, monkeypatch):
    frost = date(YEAR, 4, 15)
    monkeypatch.setenv("LAST_FROST_DATE", frost.isoformat())
    plant = make_plant(client, "Sow Test Pepper", species_type="Pepper",
                       days_to_maturity=80, status="Planned")
    res = client.get("/api/stats/seed-calendar")
    assert res.status_code == 200
    rows = {r["variety_name"]: r for r in res.json()}
    row = rows["Sow Test Pepper"]
    # peppers start 8 weeks before last frost
    assert row["suggested_start"] == (frost - timedelta(weeks=8)).isoformat()
    assert row["days_until"] == (frost - timedelta(weeks=8) - TODAY).days
    assert row["started_indoors"] is None
    assert plant["id"] == row["plant_id"]


def test_seed_calendar_default_frost_without_env(client, monkeypatch):
    monkeypatch.delenv("LAST_FROST_DATE", raising=False)
    make_plant(client, "Sow Test Tomato", species_type="Tomato",
               days_to_maturity=70, status="Planned")
    res = client.get("/api/stats/seed-calendar")
    assert res.status_code == 200
    rows = {r["variety_name"]: r for r in res.json()}
    # tomatoes: 6 weeks before the Apr-15 default
    expected = date(YEAR, 4, 15) - timedelta(weeks=6)
    assert rows["Sow Test Tomato"]["suggested_start"] == expected.isoformat()


def test_digest_sow_section():
    rows = [
        SowRow(plant_id=1, variety_name="Soon Pepper", category="",
               suggested_start=TODAY + timedelta(days=3), days_until=3,
               started_indoors=None),
        SowRow(plant_id=2, variety_name="Done Pepper", category="",
               suggested_start=TODAY, days_until=0,
               started_indoors=TODAY - timedelta(days=5)),
    ]
    msg = build_digest_message([], today=TODAY, sow_rows=rows)
    assert "Start indoors this week" in msg
    assert "Soon Pepper" in msg
    assert "Done Pepper" not in msg  # already started -> not nagged
    # no reminders + no sow rows -> all-clear still works
    assert "All clear" in build_digest_message([], today=TODAY)


# --------------------------------------------------------------------------- #
def test_quick_log_api_surface(client):
    """The exact calls the Quick Log page makes must succeed."""
    loc = client.post("/api/locations/", params={"name": "Quick bed"})
    assert loc.status_code == 201, loc.text
    plant = make_plant(client, "Quick Pepper", location_id=loc.json()["id"])

    res = client.post("/api/watering-logs/", json={
        "plant_id": plant["id"], "location_id": loc.json()["id"],
        "date": TODAY.isoformat(),
    })
    assert res.status_code == 201, res.text

    res = client.post("/api/harvests/", json={
        "plant_id": plant["id"], "date": TODAY.isoformat(),
        "quantity": 4, "unit": "fruit", "notes": "",
    })
    assert res.status_code == 201, res.text

    res = client.post("/api/observations", json={
        "plant_id": plant["id"], "plant_name": plant["variety_name"],
        "date": TODAY.isoformat(), "notes": "Looking perky", "health_scale": 7,
    })
    assert res.status_code == 201, res.text

    res = client.get("/api/watering-logs/", params={"date": TODAY.isoformat()})
    assert res.status_code == 200
    assert any(w["plant_id"] == plant["id"] for w in res.json())


# --------------------------------------------------------------------------- #
def test_frost_countdown_with_env(client, monkeypatch):
    frost = date(YEAR, 11, 15)
    monkeypatch.setenv("FIRST_FROST_DATE", frost.isoformat())
    res = client.get("/api/stats/frost")
    assert res.status_code == 200
    body = res.json()
    assert body["first_frost_date"] == frost.isoformat()
    assert body["days_until"] == (frost - TODAY).days


def test_frost_countdown_unset(client, monkeypatch):
    monkeypatch.delenv("FIRST_FROST_DATE", raising=False)
    res = client.get("/api/stats/frost")
    assert res.status_code == 200
    assert res.json() == {
        "first_frost_date": None, "days_until": None, "source": None, "label": "",
    }


def test_all_pages_render_with_base_template(client):
    """Every page returns 200 and carries the shared header/footer markers."""
    paths = ["/", "/observations", "/calendar", "/photos", "/plants", "/seeds",
             "/review", "/import", "/backup", "/slideshow", "/quick", "/costs",
             "/pests", "/settings"]
    for path in paths:
        res = client.get(path)
        assert res.status_code == 200, path
        html = res.text
        assert 'id="frost-countdown"' in html or path == "/slideshow", path
        assert "/static/js/core.js" in html, path
