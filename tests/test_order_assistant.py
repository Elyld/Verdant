"""Winter seed-order assistant tests: wishlist CRUD, grow-again ratings, and
the assembled /api/order-assistant view (stash ages, last-year vendor
spend, last vendor/date from invoices).

Run with:  pytest -q
"""
import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="order-assistant-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

LAST_YEAR = date.today().year - 1
THIS_YEAR = date.today().year


@pytest.fixture(scope="module")
def client():
    init_db()
    created = {"invoices": [], "packets": [], "wishlist": []}
    with TestClient(app) as c:
        yield c, created
    # Teardown: remove everything this module created so other test modules'
    # exact-count assertions keep passing.
    with TestClient(app) as c:
        for wid in created["wishlist"]:
            c.delete(f"/api/wishlist/{wid}")
        for inv_id in created["invoices"]:
            c.delete(f"/api/invoices/{inv_id}")
        for pkt_id in created["packets"]:
            c.delete(f"/api/seed-packets/{pkt_id}")


def _mk_packet(c, created, variety, **kw):
    payload = {"variety_name": variety}
    payload.update(kw)
    res = c.post("/api/seed-packets/", json=payload)
    assert res.status_code == 201, res.text
    created["packets"].append(res.json()["id"])
    return res.json()


def _mk_invoice(c, created, vendor, order_date, total, items_summary=""):
    res = c.post("/api/invoices/", json={
        "vendor": vendor,
        "order_date": order_date,
        "order_number": f"OA-{vendor[:3]}-{order_date}",
        "total": total,
        "items_summary": items_summary,
        "notes": "",
        "source": "manual",
    })
    assert res.status_code == 201, res.text
    created["invoices"].append(res.json()["id"])
    return res.json()


def _mk_wish(c, created, variety, **kw):
    payload = {"variety_name": variety}
    payload.update(kw)
    res = c.post("/api/wishlist/", json=payload)
    assert res.status_code == 201, res.text
    created["wishlist"].append(res.json()["id"])
    return res.json()


def test_wishlist_crud(client):
    c, created = client
    res = c.post("/api/wishlist/", json={"variety_name": "   "})
    assert res.status_code == 422
    w = _mk_wish(c, created, "OA Wishlist Tomato", vendor_name="OA Vendor")
    assert w["checked"] is False
    assert w["date_added"] == date.today().isoformat()

    res = c.get("/api/wishlist/")
    assert res.status_code == 200
    assert any(x["id"] == w["id"] for x in res.json())

    res = c.patch(f"/api/wishlist/{w['id']}", json={"checked": True, "notes": "for the big bed"})
    assert res.status_code == 200
    assert res.json()["checked"] is True
    assert res.json()["notes"] == "for the big bed"

    res = c.patch(f"/api/wishlist/{w['id']}", json={"variety_name": "  "})
    assert res.status_code == 422

    res = c.delete(f"/api/wishlist/{w['id']}")
    assert res.status_code == 204
    created["wishlist"].remove(w["id"])
    res = c.delete(f"/api/wishlist/{w['id']}")
    assert res.status_code == 404


def test_grow_again_rating(client):
    c, created = client
    p = _mk_packet(c, created, "OA Rating Pepper", year_acquired=LAST_YEAR)
    for value in ("no", "yes", "favorite", ""):
        res = c.patch(f"/api/seed-packets/{p['id']}", json={"grow_again": value})
        assert res.status_code == 200, res.text
        assert res.json()["grow_again"] == value
    res = c.patch(f"/api/seed-packets/{p['id']}", json={"grow_again": "maybe"})
    assert res.status_code == 422


def test_assistant_assembles(client):
    c, created = client
    p = _mk_packet(
        c, created, "OA Assist Tomato",
        year_acquired=LAST_YEAR - 1, vendor_name="OA Seed Co",
        quantity="~30 seeds", seed_count=30,
    )
    w = _mk_wish(c, created, "OA Wish Cucumber", vendor_name="OA Seed Co")

    # Linked invoice in last year (authoritative last order).
    inv = _mk_invoice(
        c, created, "OA Seed Co", f"{LAST_YEAR}-02-10", 51.25,
        items_summary="OA Assist Tomato - ORGANIC SEED x1 $4.95",
    )
    res = c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": p["id"]})
    assert res.status_code == 200
    # Second order from another vendor, still last year.
    _mk_invoice(c, created, "OA Other Vendor", f"{LAST_YEAR}-11-20", 18.00)
    # Current-year invoice: must NOT appear in last-year spend.
    _mk_invoice(
        c, created, "OA Seed Co", f"{THIS_YEAR}-01-05", 99.99,
        items_summary="OA Wish Cucumber x1 $3.95",
    )

    res = c.get("/api/order-assistant/")
    assert res.status_code == 200
    d = res.json()
    assert d["last_year"] == LAST_YEAR

    prow = next(x for x in d["packets"] if x["id"] == p["id"])
    assert prow["variety_name"] == "OA Assist Tomato"
    assert prow["stash_age_years"] == THIS_YEAR - (LAST_YEAR - 1)
    assert prow["grow_again"] == ""
    assert prow["seed_count"] == 30
    assert prow["last_order"]["vendor"] == "OA Seed Co"
    assert prow["last_order"]["order_date"] == f"{LAST_YEAR}-02-10"
    assert prow["last_order"]["invoice_id"] == inv["id"]

    spend = {r["vendor"]: r for r in d["vendor_spend"]}
    assert spend["OA Seed Co"]["total"] == 51.25
    assert spend["OA Seed Co"]["orders"] == 1
    assert spend["OA Other Vendor"]["total"] == 18.00
    # Sorted by total desc.
    totals = [r["total"] for r in d["vendor_spend"]]
    assert totals == sorted(totals, reverse=True)

    wrow = next(x for x in d["wishlist"] if x["id"] == w["id"])
    # No linked packet: resolved from the items_summary text mention.
    assert wrow["last_order"]["vendor"] == "OA Seed Co"
    assert wrow["last_order"]["order_date"] == f"{THIS_YEAR}-01-05"
    assert wrow["checked"] is False


def test_assistant_empty_state(client):
    c, _created = client
    res = c.get("/api/order-assistant/")
    assert res.status_code == 200
    d = res.json()
    assert isinstance(d["packets"], list)
    assert isinstance(d["wishlist"], list)
    # No invoice rows from this module: vendor_spend only counts this
    # module's invoices, which are all cleaned up on teardown; here just
    # assert the shape.
    assert isinstance(d["vendor_spend"], list)
