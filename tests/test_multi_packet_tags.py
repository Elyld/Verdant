"""Multi seed-packet tagging: multiple packets per invoice, and packet
tagging on expenses (independent link table + endpoints + suggestions).

Run with:  pytest -q
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="multi-packets-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import select  # noqa: E402

from app.database import get_session, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ExpenseSeedPacket, InvoiceSeedPacket  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    created = {"invoices": [], "expenses": [], "packets": []}
    with TestClient(app) as c:
        yield c, created
    # Teardown: remove everything this module created so other test modules'
    # exact-count assertions keep passing.
    with TestClient(app) as c:
        for inv_id in created["invoices"]:
            c.delete(f"/api/invoices/{inv_id}")
        for exp_id in created["expenses"]:
            c.delete(f"/api/expenses/{exp_id}")
        for pkt_id in created["packets"]:
            c.delete(f"/api/seed-packets/{pkt_id}")


def _mk_invoice(c, created, order_number, items_summary=""):
    res = c.post("/api/invoices/", json={
        "vendor": "MultiTest Seed Co",
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


def _mk_expense(c, created, description, notes=""):
    res = c.post("/api/expenses/", json={
        "date": "2026-09-02",
        "category": "Seeds",
        "description": description,
        "amount": 9.99,
        "notes": notes,
    })
    assert res.status_code == 201, res.text
    created["expenses"].append(res.json()["id"])
    return res.json()


def _mk_packet(c, created, variety):
    res = c.post("/api/seed-packets/", json={"variety_name": variety, "vendor_name": "MultiTest"})
    assert res.status_code == 201, res.text
    created["packets"].append(res.json()["id"])
    return res.json()


def test_invoice_multi_attach_persists(client):
    c, created = client
    inv = _mk_invoice(c, created, "MULTI-001")
    p1 = _mk_packet(c, created, "MultiTest Tomato Alpha")
    p2 = _mk_packet(c, created, "MultiTest Pepper Beta")
    p3 = _mk_packet(c, created, "MultiTest Basil Gamma")

    for p in (p1, p2, p3):
        res = c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": p["id"]})
        assert res.status_code == 200, res.text

    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert res.status_code == 200
    assert sorted(p["id"] for p in res.json()) == sorted([p1["id"], p2["id"], p3["id"]])

    # Re-attaching one of them is still a no-op.
    res = c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": p1["id"]})
    assert res.status_code == 200
    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert len(res.json()) == 3


def test_expense_packet_crud(client):
    c, created = client
    exp = _mk_expense(c, created, "MultiTest order")
    p1 = _mk_packet(c, created, "MultiTest Expense Tomato")
    p2 = _mk_packet(c, created, "MultiTest Expense Pepper")

    res = c.get(f"/api/expenses/{exp['id']}/packets")
    assert res.status_code == 200 and res.json() == []

    res = c.post(f"/api/expenses/{exp['id']}/packets", json={"seed_packet_id": p1["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["variety_name"] == "MultiTest Expense Tomato"

    # Idempotent re-attach.
    res = c.post(f"/api/expenses/{exp['id']}/packets", json={"seed_packet_id": p1["id"]})
    assert res.status_code == 200

    res = c.post(f"/api/expenses/{exp['id']}/packets", json={"seed_packet_id": p2["id"]})
    assert res.status_code == 200
    res = c.get(f"/api/expenses/{exp['id']}/packets")
    assert sorted(p["id"] for p in res.json()) == sorted([p1["id"], p2["id"]])

    res = c.delete(f"/api/expenses/{exp['id']}/packets/{p1['id']}")
    assert res.status_code == 204, res.text
    res = c.get(f"/api/expenses/{exp['id']}/packets")
    assert [p["id"] for p in res.json()] == [p2["id"]]

    # Detaching what's not linked is a 404, not a silent no-op.
    res = c.delete(f"/api/expenses/{exp['id']}/packets/{p1['id']}")
    assert res.status_code == 404


def test_expense_packet_validation(client):
    c, created = client
    exp = _mk_expense(c, created, "MultiTest validation")
    pkt = _mk_packet(c, created, "MultiTest Validation Tomato")

    res = c.post("/api/expenses/999999/packets", json={"seed_packet_id": pkt["id"]})
    assert res.status_code == 404
    res = c.post(f"/api/expenses/{exp['id']}/packets", json={"seed_packet_id": 999999})
    assert res.status_code in (404, 422)
    res = c.post(f"/api/expenses/{exp['id']}/packets", json={})
    assert res.status_code == 422
    res = c.get("/api/expenses/999999/packets")
    assert res.status_code == 404
    res = c.get("/api/expenses/999999/packet-suggestions")
    assert res.status_code == 404


def test_expense_suggestions_match_notes(client):
    c, created = client
    p1 = _mk_packet(c, created, "MultiTest Suggest Tomato")
    p2 = _mk_packet(c, created, "MultiTest Suggest Pepper")
    exp = _mk_expense(
        c, created, "MultiTest Seed Co — order 77",
        notes="MultiTest Suggest Tomato - ORGANIC SEED / 1/8 gram x1 $4.95; "
              "MultiTest Suggest Pepper - SEED / 25 seeds x1 $5.04",
    )

    res = c.get(f"/api/expenses/{exp['id']}/packet-suggestions")
    assert res.status_code == 200, res.text
    ids = [s["packet_id"] for s in res.json()]
    assert p1["id"] in ids and p2["id"] in ids

    # Already-linked packets are excluded from suggestions.
    c.post(f"/api/expenses/{exp['id']}/packets", json={"seed_packet_id": p1["id"]})
    res = c.get(f"/api/expenses/{exp['id']}/packet-suggestions")
    ids = [s["packet_id"] for s in res.json()]
    assert p1["id"] not in ids and p2["id"] in ids


def test_expense_delete_cascades_links(client):
    c, created = client
    exp = _mk_expense(c, created, "MultiTest doomed")
    pkt = _mk_packet(c, created, "MultiTest Doomed Tomato")
    c.post(f"/api/expenses/{exp['id']}/packets", json={"seed_packet_id": pkt["id"]})

    res = c.delete(f"/api/expenses/{exp['id']}")
    assert res.status_code == 204, res.text
    created["expenses"].remove(exp["id"])

    session = next(get_session())
    try:
        leftover = session.exec(
            select(ExpenseSeedPacket).where(ExpenseSeedPacket.expense_id == exp["id"])
        ).all()
    finally:
        session.close()
    assert leftover == []


def test_invoice_and_expense_tags_are_independent(client):
    c, created = client
    inv = _mk_invoice(c, created, "MULTI-IND-001")
    exp = _mk_expense(c, created, "MultiTest independent")
    p1 = _mk_packet(c, created, "MultiTest Independent Tomato")
    p2 = _mk_packet(c, created, "MultiTest Independent Pepper")

    c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": p1["id"]})
    c.post(f"/api/expenses/{exp['id']}/packets", json={"seed_packet_id": p2["id"]})

    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert [p["id"] for p in res.json()] == [p1["id"]]
    res = c.get(f"/api/expenses/{exp['id']}/packets")
    assert [p["id"] for p in res.json()] == [p2["id"]]

    # Deleting the invoice must not touch the expense's links.
    c.delete(f"/api/invoices/{inv['id']}")
    created["invoices"].remove(inv["id"])
    res = c.get(f"/api/expenses/{exp['id']}/packets")
    assert [p["id"] for p in res.json()] == [p2["id"]]


def _csv(text):
    return {"file": ("data.csv", io.BytesIO(text.encode("utf-8-sig")), "text/csv")}


MULTI_CSV = """Vendor,Order Number,Order Date,Total,Items,Notes
MultiTest Seed Co,MULTI-IMP-001,2026-09-03,9.99,"MultiTest Csv Tomato - ORGANIC SEED / 1/8 gram x1 $4.95; MultiTest Csv Pepper - SEED / 25 seeds x1 $5.04",
"""


def test_import_run_links_multiple_packets(client):
    c, created = client
    p1 = _mk_packet(c, created, "MultiTest Csv Tomato")
    p2 = _mk_packet(c, created, "MultiTest Csv Pepper")

    data = {
        "entity": "invoices",
        "assignments": json.dumps({}),
        "packet_assignments": json.dumps({"inv:0": [p1["id"], p2["id"]]}),
    }
    res = c.post("/api/import/run", data=data, files=_csv(MULTI_CSV))
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 1

    res = c.get("/api/invoices/", params={"vendor": "MultiTest Seed Co"})
    inv = next(i for i in res.json() if i["order_number"] == "MULTI-IMP-001")
    created["invoices"].append(inv["id"])

    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert sorted(p["id"] for p in res.json()) == sorted([p1["id"], p2["id"]])


def test_seed_packet_delete_cascades_both_link_tables(client):
    c, created = client
    inv = _mk_invoice(c, created, "MULTI-CAS-001")
    exp = _mk_expense(c, created, "MultiTest cascade")
    pkt = _mk_packet(c, created, "MultiTest Cascade Tomato")
    c.post(f"/api/invoices/{inv['id']}/packets", json={"seed_packet_id": pkt["id"]})
    c.post(f"/api/expenses/{exp['id']}/packets", json={"seed_packet_id": pkt["id"]})

    res = c.delete(f"/api/seed-packets/{pkt['id']}")
    assert res.status_code in (200, 204), res.text
    created["packets"].remove(pkt["id"])

    res = c.get(f"/api/invoices/{inv['id']}/packets")
    assert res.json() == []
    res = c.get(f"/api/expenses/{exp['id']}/packets")
    assert res.json() == []
