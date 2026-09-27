"""Expense editing + vendor-aware invoice categories.

- category_for_invoice maps vendors (247Garden -> Supplies, seed vendors ->
  Seeds) with keyword fallback on the items text, defaulting to Seeds.
- auto_create_expense uses the mapped category.
- DELETE /api/expenses/{id} unlinks invoices instead of 500ing on the FK.
- PATCHing an invoice syncs amount/date/description but never the category,
  so a hand-changed category sticks.

Run with:  pytest -q
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

TMP = Path(tempfile.mkdtemp(prefix="expense-editing-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.invoice_expenses import category_for_invoice  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    created = {"invoices": [], "expenses": []}
    with TestClient(app) as c:
        yield c, created
    # Teardown: invoice deletes cascade their auto-created expenses; anything
    # left (manually created or unlinked) is removed explicitly. Keeps other
    # modules' exact-count assertions green on the shared test DB.
    with TestClient(app) as c:
        for inv_id in created["invoices"]:
            c.delete(f"/api/invoices/{inv_id}")
        for exp_id in created["expenses"]:
            c.delete(f"/api/expenses/{exp_id}")


def _inv(vendor="", items_summary="", notes=""):
    return SimpleNamespace(vendor=vendor, items_summary=items_summary, notes=notes)


# --- category_for_invoice -------------------------------------------------


def test_vendor_247garden_is_supplies():
    assert category_for_invoice(_inv(vendor="247Garden")) == "Supplies"
    assert category_for_invoice(_inv(vendor="247GARDEN")) == "Supplies"
    assert category_for_invoice(_inv(vendor="247garden.com")) == "Supplies"


def test_seed_vendors_are_seeds():
    for vendor in ("Territorial Seed Company", "Seed Savers Exchange",
                   "True Leaf Market", "Matt's Peppers"):
        assert category_for_invoice(_inv(vendor=vendor)) == "Seeds", vendor


def test_keyword_fallback():
    assert category_for_invoice(_inv(items_summary="5-gallon grow bags x4")) == "Supplies"
    assert category_for_invoice(_inv(items_summary="10-10-10 fertilizer 5lb")) == "Fertilizer"
    assert category_for_invoice(_inv(items_summary="organic potting mix 2 cu ft")) == "Soil"
    # "pot" must not match inside other words like "potato".
    assert category_for_invoice(_inv(items_summary="potato seeds")) == "Seeds"
    assert category_for_invoice(_inv(items_summary="3 gal pots x6")) == "Supplies"


def test_vendor_wins_over_keywords():
    inv = _inv(vendor="Territorial Seed", items_summary="grow bags x4")
    assert category_for_invoice(inv) == "Seeds"


def test_default_is_seeds():
    assert category_for_invoice(_inv(vendor="Some Random Shop")) == "Seeds"
    assert category_for_invoice(_inv()) == "Seeds"


# --- API behavior ----------------------------------------------------------


def _payload(order_number, **over):
    base = {
        "vendor": "CategoryTest Co",
        "order_date": "2026-09-10",
        "order_number": order_number,
        "total": 48.02,
        "items_summary": "fabric grow bags x4",
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


def _get_expense(c, exp_id):
    matches = [e for e in c.get("/api/expenses/").json() if e["id"] == exp_id]
    assert matches, f"expense {exp_id} not found"
    return matches[0]


def _get_invoice(c, inv_id):
    """No GET-one invoice endpoint; pull from the list."""
    matches = [i for i in c.get("/api/invoices/").json() if i["id"] == inv_id]
    assert matches, f"invoice {inv_id} not found"
    return matches[0]


def test_auto_create_uses_vendor_category(client):
    c, created = client
    inv = _mk_invoice(c, created, "CAT-1", vendor="247Garden",
                      items_summary="7-gallon grow bags x4")
    body = _get_expense(c, inv["expense_id"])
    assert body["category"] == "Supplies"


def test_auto_create_keyword_category(client):
    c, created = client
    inv = _mk_invoice(c, created, "CAT-2", vendor="Unknown Vendor",
                      items_summary="10-10-10 all-purpose fertilizer")
    body = _get_expense(c, inv["expense_id"])
    assert body["category"] == "Fertilizer"


def test_expense_delete_unlinks_invoice(client):
    c, created = client
    inv = _mk_invoice(c, created, "CAT-3")
    exp_id = inv["expense_id"]
    assert exp_id, "expected an auto-created expense"

    res = c.delete(f"/api/expenses/{exp_id}")
    assert res.status_code == 204, res.text

    # Invoice survives, cleanly unlinked — no 500, no dangling FK.
    after = _get_invoice(c, inv["id"])
    assert after["expense_id"] is None
    assert after["expense_auto_created"] is False


def test_invoice_patch_sync_never_touches_category(client):
    c, created = client
    inv = _mk_invoice(c, created, "CAT-4", vendor="Territorial Seed")
    exp_id = inv["expense_id"]
    assert _get_expense(c, exp_id)["category"] == "Seeds"

    # Hand-change the category, then edit the invoice: amount syncs, category sticks.
    res = c.patch(f"/api/expenses/{exp_id}", json={"category": "Supplies"})
    assert res.status_code == 200, res.text
    assert res.json()["category"] == "Supplies"

    res = c.patch(f"/api/invoices/{inv['id']}", json={"total": 99.99})
    assert res.status_code == 200, res.text

    body = _get_expense(c, exp_id)
    assert body["amount"] == 99.99
    assert body["category"] == "Supplies", "invoice PATCH sync must not overwrite category"


def test_expense_patch_rejects_bad_category(client):
    c, created = client
    inv = _mk_invoice(c, created, "CAT-5")
    res = c.patch(f"/api/expenses/{inv['expense_id']}", json={"category": "Bogus"})
    assert res.status_code == 422
