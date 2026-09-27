"""Invoice -> expense auto-creation tests.

Creating an invoice without an expense link auto-creates the backing expense;
edits sync onto it and deletes take it along. Manually linked expenses are
never touched. Re-imports and repeat calls never create dupes.

Run with:  pytest -q
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="invoice-expenses-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    created = {"invoices": [], "expenses": []}
    with TestClient(app) as c:
        yield c, created
    # Teardown: invoice deletes cascade their auto-created expenses; manually
    # linked expenses are removed explicitly. Keeps other modules' exact-count
    # assertions green on the shared test DB.
    with TestClient(app) as c:
        for inv_id in created["invoices"]:
            c.delete(f"/api/invoices/{inv_id}")
        for exp_id in created["expenses"]:
            c.delete(f"/api/expenses/{exp_id}")


def _payload(order_number, **over):
    base = {
        "vendor": "ExpenseTest Seed Co",
        "order_date": "2026-09-10",
        "order_number": order_number,
        "total": 42.50,
        "items_summary": "Test Tomato seeds, Test Pepper seeds",
        "notes": "",
        "source": "manual",
    }
    base.update(over)
    return base


def _mk_invoice(c, created, order_number, **over):
    res = c.post("/api/invoices/", json=_payload(order_number, **over))
    assert res.status_code == 201, res.text
    created["invoices"].append(res.json()["id"])
    return res.json()


def _expense_count(c):
    return len(c.get("/api/expenses/").json())


def _get_expense(c, exp_id):
    """No GET-one expense endpoint; pull from the list."""
    matches = [e for e in c.get("/api/expenses/").json() if e["id"] == exp_id]
    assert matches, f"expense {exp_id} not found"
    return matches[0]


def _expense_gone(c, exp_id):
    return not any(e["id"] == exp_id for e in c.get("/api/expenses/").json())


def test_post_auto_creates_expense(client):
    c, created = client
    inv = _mk_invoice(c, created, "EXP-AUTO-1")
    assert inv["expense_id"], "invoice should link an auto-created expense"
    assert inv["expense_auto_created"] is True

    body = _get_expense(c, inv["expense_id"])
    assert body["amount"] == 42.50
    assert body["date"] == "2026-09-10"
    assert body["category"] == "Seeds"
    assert "ExpenseTest Seed Co" in body["description"]
    assert "EXP-AUTO-1" in body["description"]
    assert "Test Tomato seeds" in (body["notes"] or "")


def test_post_with_manual_link_creates_nothing(client):
    c, created = client
    before = _expense_count(c)
    exp = c.post(
        "/api/expenses/",
        json={"date": "2026-09-10", "category": "Seeds",
              "description": "manual", "amount": 10.0},
    )
    assert exp.status_code == 201, exp.text
    exp_id = exp.json()["id"]
    created["expenses"].append(exp_id)

    inv = _mk_invoice(c, created, "EXP-AUTO-2", expense_id=exp_id)
    assert inv["expense_id"] == exp_id
    assert inv["expense_auto_created"] is False
    assert _expense_count(c) == before + 1, "only the manual expense should exist"


def test_create_expense_endpoint_idempotent(client):
    c, created = client
    # Build the invoice through the DB-neutral path: POST auto-creates, so
    # strip the link first via PATCH to exercise the endpoint from scratch.
    inv = _mk_invoice(c, created, "EXP-AUTO-3")
    orphan_exp = inv["expense_id"]
    c.patch(f"/api/invoices/{inv['id']}", json={"expense_id": None})
    before = _expense_count(c)

    r1 = c.post(f"/api/invoices/{inv['id']}/create-expense")
    assert r1.status_code == 200, r1.text
    assert r1.json()["expense_id"]
    assert r1.json()["expense_auto_created"] is True
    assert _expense_count(c) == before + 1

    r2 = c.post(f"/api/invoices/{inv['id']}/create-expense")
    assert r2.status_code == 200, r2.text
    assert r2.json()["expense_id"] == r1.json()["expense_id"]
    assert _expense_count(c) == before + 1, "second call must not dupe"

    # Already linked -> returned unchanged, no new expense.
    r3 = c.post(f"/api/invoices/{inv['id']}/create-expense")
    assert r3.status_code == 200
    assert _expense_count(c) == before + 1
    # The expense orphaned by the unlink PATCH above is this module's to clean.
    created["expenses"].append(orphan_exp)


def test_patch_syncs_auto_expense(client):
    c, created = client
    inv = _mk_invoice(c, created, "EXP-AUTO-4")
    exp_id = inv["expense_id"]

    res = c.patch(f"/api/invoices/{inv['id']}",
                  json={"total": 99.99, "vendor": "Renamed Seed Co"})
    assert res.status_code == 200, res.text

    exp = _get_expense(c, exp_id)
    assert exp["amount"] == 99.99
    assert "Renamed Seed Co" in exp["description"]
    assert "EXP-AUTO-4" in exp["description"]

    # Manual re-link flips the flag; the old auto expense is kept, not deleted.
    manual = c.post(
        "/api/expenses/",
        json={"date": "2026-09-10", "category": "Supplies",
              "description": "manual 2", "amount": 5.0},
    ).json()
    created["expenses"].append(manual["id"])
    res = c.patch(f"/api/invoices/{inv['id']}", json={"expense_id": manual["id"]})
    assert res.json()["expense_auto_created"] is False
    assert not _expense_gone(c, exp_id)
    # The superseded auto expense is kept by design; clean it here so the
    # shared DB stays tidy.
    created["expenses"].append(exp_id)


def test_delete_removes_auto_expense_but_keeps_manual(client):
    c, created = client
    auto = _mk_invoice(c, created, "EXP-AUTO-5")
    auto_exp = auto["expense_id"]
    created["invoices"].remove(auto["id"])  # deleted below, not in teardown

    manual_exp = c.post(
        "/api/expenses/",
        json={"date": "2026-09-10", "category": "Seeds",
              "description": "manual 3", "amount": 7.0},
    ).json()["id"]
    created["expenses"].append(manual_exp)
    manual = _mk_invoice(c, created, "EXP-AUTO-6", expense_id=manual_exp)
    created["invoices"].remove(manual["id"])

    assert c.delete(f"/api/invoices/{auto['id']}").status_code == 204
    assert _expense_gone(c, auto_exp)

    assert c.delete(f"/api/invoices/{manual['id']}").status_code == 204
    assert not _expense_gone(c, manual_exp)


def _csv(text):
    return {"file": ("data.csv", io.BytesIO(text.encode("utf-8-sig")), "text/csv")}


IMPORT_CSV = """Vendor,Order Number,Order Date,Total,Items,Notes
ExpenseTest Seed Co,EXP-CSV-1,2026-09-11,15.25,CSV Tomato seeds,
ExpenseTest Seed Co,EXP-CSV-2,2026-09-12,20.00,CSV Pepper seeds,
"""


def test_csv_import_creates_expenses_no_dupes(client):
    c, created = client
    data = {"entity": "invoices", "assignments": json.dumps({})}
    before = _expense_count(c)

    res = c.post("/api/import/run", data=data, files=_csv(IMPORT_CSV))
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 2, res.json()
    assert _expense_count(c) == before + 2

    for order_no, total, when in (("EXP-CSV-1", 15.25, "2026-09-11"),
                                  ("EXP-CSV-2", 20.00, "2026-09-12")):
        inv = next(i for i in c.get("/api/invoices/").json()
                   if i["order_number"] == order_no)
        created["invoices"].append(inv["id"])
        assert inv["expense_auto_created"] is True
        exp = _get_expense(c, inv["expense_id"])
        assert exp["amount"] == total and exp["date"] == when

    # Re-run: skipped, no new invoices, no new expenses.
    res = c.post("/api/import/run", data=data, files=_csv(IMPORT_CSV))
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 0 and res.json()["skipped"] == 2
    assert _expense_count(c) == before + 2
