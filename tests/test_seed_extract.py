"""Seed-packet derivation from invoice line items: the extractor's
normalization rules plus the derive-packets API (preview, apply, idempotency,
matching to existing packets).

Run with:  pytest -q
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="seed-extract-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed_extract import (  # noqa: E402
    candidates_from_invoice,
    derive_packet,
    is_seed_item,
    parse_line_items,
)

# --------------------------------------------------------------------------- #
# Extractor unit tests
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name,category,variety", [
    ("Pepper, Purple Beauty", "Pepper", "Purple Beauty"),
    ("Herb, Garlic Chives", "Herb", "Garlic Chives"),
    ("Sunflower, Sunflower Mixture", "Sunflower", "Sunflower Mixture"),
    ("Ground Cherry, Loewen Family Heirloom (organic)", "Ground Cherry", "Loewen Family Heirloom"),
    ("RING OF FIRE - SEED / 1/2 gram", "", "Ring Of Fire"),
    ("BUSH DELICATA - SEED / 3 grams", "Summer Squash", "Bush Delicata"),
    ("Fall Garlic Festival - GARLIC / three 8 oz pkgs", "Garlic", "Fall Garlic Festival"),
    ("Tobacco Seeds - KY 15 100 seeds", "Tobacco", "Ky 15"),
    ("Chinese Lantern – 50 Seeds", "Flower", "Chinese Lantern"),
    ("Bunny Tails – 50 Seeds", "Flower", "Bunny Tails"),
    ("Bishop's Crown Peach", "", "Bishop's Crown Peach"),
    ("BUFFY - SEED / 25 seeds", "", "Buffy"),
])
def test_derive_variety_and_category(name, category, variety):
    p = derive_packet(name, vendor="V")
    assert p["category"] == category, (name, p)
    assert p["variety_name"] == variety, (name, p)


def test_pea_not_matched_inside_peach():
    # "peach" must not trip the Pea keyword; vendor hint supplies Pepper.
    p = derive_packet("Bishop's Crown Peach", vendor="Matt's Peppers")
    assert p["category"] == "Pepper"


def test_containers_and_supplies_are_not_seeds():
    for name in (
        "10-Gallon Square Aeration Fabric Pot Planting Grow Bag w/Handles",
        "15-Gallon Tall Aeration Fabric Pot/Tree Grow Bag (Black w/Green Handles)",
        "Seed Starting Mix",
        "Bamboo Plant Stake 4ft",
    ):
        assert is_seed_item(name) is False, name
    assert is_seed_item("Pepper, Purple Beauty") is True


def test_parse_line_items_extracts_qty_price():
    items = parse_line_items("Pepper, Fatalii x1 $4.25; RING OF FIRE - SEED / 1/2 gram x1 $3.85")
    assert [i["name"] for i in items] == [
        "Pepper, Fatalii", "RING OF FIRE - SEED / 1/2 gram",
    ]
    assert items[0]["qty"] == 1 and items[0]["price"] == 4.25
    assert items[1]["price"] == 3.85


def test_candidates_skip_containers():
    summary = (
        "10-Gallon Aeration Fabric Pot Grow Bag x6 $9.00; "
        "Pepper, Fatalii x1 $4.25"
    )
    cands = candidates_from_invoice(summary, "Vendor", "2026-01-02")
    assert [c["variety_name"] for c in cands] == ["Fatalii"]
    assert cands[0]["year_acquired"] == 2026


# --------------------------------------------------------------------------- #
# API tests
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def client():
    init_db()
    created = {"invoices": [], "packets": []}
    with TestClient(app) as c:
        yield c, created
    with TestClient(app) as c:
        for inv_id in created["invoices"]:
            c.delete(f"/api/invoices/{inv_id}")
        for pkt_id in created["packets"]:
            c.delete(f"/api/seed-packets/{pkt_id}")


def _mk_invoice(c, created, order_number, items_summary, vendor="DeriveTest Seed Co",
                order_date="2026-09-01"):
    res = c.post("/api/invoices/", json={
        "vendor": vendor, "order_date": order_date, "order_number": order_number,
        "total": 20.0, "items_summary": items_summary, "notes": "", "source": "manual",
    })
    assert res.status_code == 201, res.text
    created["invoices"].append(res.json()["id"])
    return res.json()


def test_derive_preview_does_not_write(client):
    c, created = client
    inv = _mk_invoice(c, created, "DER-001",
                      "DeriveTest Suggestion Tomato x1 $4.95")
    res = c.post(f"/api/invoices/{inv['id']}/derive-packets", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["applied"] is False
    assert body["created"] == []
    assert [p["variety_name"] for p in body["plan"]] == ["DeriveTest Suggestion Tomato"]
    # Nothing was written: no packet links exist yet.
    assert c.get(f"/api/invoices/{inv['id']}/packets").json() == []


def test_derive_apply_creates_and_links_then_idempotent(client):
    c, created = client
    inv = _mk_invoice(
        c, created, "DER-002",
        "DeriveTest Alpha Pepper x1 $4.25; DeriveTest Beta Basil x1 $4.25",
    )
    res = c.post(f"/api/invoices/{inv['id']}/derive-packets", json={"apply": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["created"]) == 2
    created["packets"].extend(body["created"])

    linked = c.get(f"/api/invoices/{inv['id']}/packets").json()
    assert {p["variety_name"] for p in linked} == {
        "DeriveTest Alpha Pepper", "DeriveTest Beta Basil",
    }
    # Categories inferred from the names.
    stash = {p["variety_name"]: p for p in c.get("/api/seed-packets/").json()}
    assert stash["DeriveTest Alpha Pepper"]["category"] == "Pepper"
    assert stash["DeriveTest Beta Basil"]["category"] == "Herb"

    # Re-running changes nothing: no new packets, same two links.
    res = c.post(f"/api/invoices/{inv['id']}/derive-packets", json={"apply": True})
    assert res.json()["created"] == []
    linked2 = c.get(f"/api/invoices/{inv['id']}/packets").json()
    assert {p["id"] for p in linked2} == {p["id"] for p in linked}


def test_derive_links_existing_packet_instead_of_duplicating(client):
    c, created = client
    # A pre-existing packet the derived variety should match (token subset).
    res = c.post("/api/seed-packets/", json={
        "variety_name": "DeriveTest Roma Tomato", "vendor_name": "DeriveTest Seed Co",
    })
    assert res.status_code == 201, res.text
    existing = res.json()
    created["packets"].append(existing["id"])

    inv = _mk_invoice(c, created, "DER-003", "DeriveTest Roma x1 $3.00")
    res = c.post(f"/api/invoices/{inv['id']}/derive-packets", json={"apply": True})
    body = res.json()
    assert body["created"] == []  # no near-duplicate created
    assert body["plan"][0]["action"] == "link"
    assert body["plan"][0]["packet_id"] == existing["id"]
    linked = c.get(f"/api/invoices/{inv['id']}/packets").json()
    assert [p["id"] for p in linked] == [existing["id"]]


def test_derive_404_and_empty(client):
    c, created = client
    assert c.post("/api/invoices/999999/derive-packets", json={}).status_code == 404
    # An invoice with only container lines yields an empty plan.
    inv = _mk_invoice(c, created, "DER-004", "10-Gallon Aeration Fabric Pot Grow Bag x6 $9.00")
    body = c.post(f"/api/invoices/{inv['id']}/derive-packets", json={"apply": True}).json()
    assert body["plan"] == [] and body["created"] == []
