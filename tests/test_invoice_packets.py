"""Invoice <-> seed packet link tests: attach/detach API, suggestions,
cascade on invoice delete, and import preview/run packet linking.

Run with:  pytest -q
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="invoice-packets-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import select  # noqa: E402

from app.database import get_session, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import InvoiceSeedPacket  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    created = {"invoices": [], "packets": []}
    with TestClient(app) as c:
        yield c, created
    # Teardown: remove everything this module created so other test modules'
    # exact-count assertions keep passing.
    with TestClient(app) as c:
        for inv_id in created["invoices"]:
            c.delete(f"/api/invoices/{inv_id}")
        for pkt_id in created["packets"]:
            c.delete(f"/api/seed-packets/{pkt_id}")


def _mk_invoice(c, created, order_number, items_summary=""):
    res = c.post("/api/invoices/", json={
        "vendor": "LinkTest Seed Co",
        "order_date": "2026-09-01",
        "order_number": order_number,
        "total": 12.34,
        "items_summary": items_summary,
        "notes": "",
        "source": "manual",
    })
    assert res.status_code == 201, res.text
    created["invoices"].append(res.json()["id"])
    return res.json()


def _mk_packet(c, created, variety):
    res = c.post("/api/seed-packets/", json={"variety_name": variety, "vendor_name": "LinkTest"})
    assert res.status_code == 201, res.text
    created["packets"].append(res.json()["id"])
    return res.json()


def test_attach_detach_idempotent(client):
    c, created = client
    inv = _mk_invoice(c, created, "LINK-001")
    pkt = _mk_packet(c, created, "LinkTest Costoluto")

    res = c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": pkt["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["variety_name"] == "LinkTest Costoluto"

    # Re-attaching the same pair is a no-op, not a duplicate.
    res = c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": pkt["id"]})
    assert res.status_code == 200, res.text

    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert res.status_code == 200
    assert [p["id"] for p in res.json()] == [pkt["id"]]

    res = c.delete(f"/api/invoices/{inv['id']}/packets/{pkt['id']}")
    assert res.status_code == 204, res.text

    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert res.json() == []

    # Detaching twice is a 404, not a 500.
    res = c.delete(f"/api/invoices/{inv['id']}/packets/{pkt['id']}")
    assert res.status_code == 404


def test_attach_validation(client):
    c, created = client
    inv = _mk_invoice(c, created, "LINK-002")
    pkt = _mk_packet(c, created, "LinkTest Habanero")

    res = c.post("/api/invoices/999999/packets", json={"seed_packet_id": pkt["id"]})
    assert res.status_code == 404
    res = c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": 999999})
    assert res.status_code == 404
    res = c.post(f"/api/invoices/{inv['id']}/packets", json={})
    assert res.status_code == 422


def test_suggestions_match_and_exclude_linked(client):
    c, created = client
    costoluto = _mk_packet(c, created, "LinkTest Suggestion Tomato")
    _mk_packet(c, created, "LinkTest Unrelated Pepper")
    inv = _mk_invoice(
        c, created, "LINK-003",
        items_summary="LinkTest Suggestion Tomato - ORGANIC SEED / 1/8 gram x1 $4.95; "
                      "LinkTest Garlic Festival - GARLIC / three 8 oz pkgs x1 $46.95",
    )

    res = c.get(f"/api/invoices/{inv['id']}/packet-suggestions")
    assert res.status_code == 200, res.text
    suggs = res.json()
    assert suggs, "expected at least one suggestion"
    top = suggs[0]
    assert top["packet_id"] == costoluto["id"]
    assert top["variety"] == "LinkTest Suggestion Tomato"
    assert "LinkTest Suggestion Tomato" in top["matched_item"]
    assert top["score"] > 0

    # Once linked, the packet drops out of the suggestions.
    res = c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": costoluto["id"]})
    assert res.status_code == 200
    res = c.get(f"/api/invoices/{inv['id']}/packet-suggestions")
    assert all(s["packet_id"] != costoluto["id"] for s in res.json())

    # An invoice with no items text yields no suggestions.
    plain = _mk_invoice(c, created, "LINK-004")
    res = c.get(f"/api/invoices/{plain['id']}/packet-suggestions")
    assert res.status_code == 200 and res.json() == []


def test_invoice_delete_cascades_links(client):
    c, created = client
    inv = _mk_invoice(c, created, "LINK-005")
    pkt = _mk_packet(c, created, "LinkTest Cascade Pepper")
    res = c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": pkt["id"]})
    assert res.status_code == 200

    res = c.delete(f"/api/invoices/{inv['id']}")
    assert res.status_code == 204, res.text
    created["invoices"].remove(inv["id"])

    session = next(get_session())
    try:
        leftover = session.exec(
            select(InvoiceSeedPacket).where(InvoiceSeedPacket.invoice_id == inv["id"])
        ).all()
    finally:
        session.close()
    assert leftover == []


def _csv(text):
    return {"file": ("data.csv", io.BytesIO(text.encode("utf-8-sig")), "text/csv")}


INVOICES_CSV = """Vendor,Order Number,Order Date,Total,Items,Notes
LinkTest Seed Co,LINK-IMP-001,2026-09-02,9.99,"LinkTest Import Tomato - ORGANIC SEED / 1/8 gram x1 $4.95; LinkTest Import Pepper - SEED / 25 seeds x1 $5.04",
"""


def test_import_preview_suggests_packets(client):
    c, created = client
    pkt = _mk_packet(c, created, "LinkTest Import Tomato")

    res = c.post("/api/import/preview", data={"entity": "invoices"}, files=_csv(INVOICES_CSV))
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["counts"]["new"] == 1
    rows = payload["packet_assign_rows"]
    assert len(rows) == 1
    assert rows[0]["key"] == "inv:0"
    assert any(s["packet_id"] == pkt["id"] for s in rows[0]["suggestions"])
    assert payload["suggested_packets"]["inv:0"] == pkt["id"]
    assert any(o["id"] == pkt["id"] for o in payload["packet_options"])


def test_import_run_links_chosen_packet(client):
    c, created = client
    pkt = _mk_packet(c, created, "LinkTest Run Tomato")

    data = {
        "entity": "invoices",
        "assignments": json.dumps({}),
        "packet_assignments": json.dumps({"inv:0": pkt["id"]}),
    }
    res = c.post("/api/import/run", data=data, files=_csv(INVOICES_CSV))
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 1

    res = c.get("/api/invoices/", params={"vendor": "LinkTest Seed Co"})
    inv = next(i for i in res.json() if i["order_number"] == "LINK-IMP-001")
    created["invoices"].append(inv["id"])

    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert [p["id"] for p in res.json()] == [pkt["id"]]

    # Re-running the same file skips the invoice and adds no duplicate links.
    res = c.post("/api/import/run", data=data, files=_csv(INVOICES_CSV))
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 0
    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert [p["id"] for p in res.json()] == [pkt["id"]]
