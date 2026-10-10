"""Invoice tests: CRUD, PDF upload/reject, expense linking, CSV import idempotency.

Run with:  pytest -q
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="invoices-test-"))
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


def _payload(**over):
    base = {
        "vendor": "Territorial Seed",
        "order_date": "2026-08-24",
        "order_number": "WW1149159",
        "total": 52.12,
        "items_summary": "Fall Garlic Festival, Costoluto Fiorentino Tomato",
        "notes": "",
        "source": "manual",
    }
    base.update(over)
    return base


def test_create_and_list(client):
    res = client.post("/api/invoices/", json=_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["vendor"] == "Territorial Seed"
    assert body["order_number"] == "WW1149159"
    assert body["total"] == 52.12
    inv_id = body["id"]
    # POST auto-creates the backing expense; the response links it.
    assert body["expense_id"]

    res = client.get("/api/invoices/")
    assert res.status_code == 200
    assert any(i["order_number"] == "WW1149159" for i in res.json())

    res = client.get("/api/invoices/", params={"vendor": "territorial"})
    assert res.status_code == 200
    assert all("territorial" in i["vendor"].lower() for i in res.json())

    # Clean up: deleting the invoice takes its auto-created expense with it,
    # keeping the shared test DB tidy for other modules' count assertions.
    res = client.delete(f"/api/invoices/{inv_id}")
    assert res.status_code == 204


def test_bad_source_rejected(client):
    res = client.post("/api/invoices/", json=_payload(order_number="WW-BAD", source="pigeon"))
    assert res.status_code == 422


def test_list_filters_and_sort(client):
    ids = []
    try:
        for vendor, num, total, source in [
            ("Territorial Seed", "WW-F1", 10.00, "manual"),
            ("Baker Creek", "BC-F2", 30.00, "gmail"),
            ("Territorial Seed", "WW-F3", 20.00, "csv"),
        ]:
            res = client.post("/api/invoices/", json=_payload(
                vendor=vendor, order_number=num, total=total, source=source,
                items_summary=f"seeds {num}",
            ))
            assert res.status_code == 201, res.text
            ids.append(res.json()["id"])

        # q searches vendor, order number, and items.
        res = client.get("/api/invoices/", params={"q": "BC-F2"})
        assert res.status_code == 200
        got = res.json()
        assert len(got) == 1 and got[0]["order_number"] == "BC-F2"

        res = client.get("/api/invoices/", params={"q": "territorial"})
        assert len(res.json()) == 2

        # source filter.
        res = client.get("/api/invoices/", params={"source": "gmail"})
        assert res.status_code == 200
        assert all(i["source"] == "gmail" for i in res.json())
        assert any(i["order_number"] == "BC-F2" for i in res.json())

        res = client.get("/api/invoices/", params={"source": "pigeon"})
        assert res.status_code == 422

        # sort by total descending / ascending.
        res = client.get("/api/invoices/", params={"sort": "total", "order": "desc"})
        totals = [i["total"] for i in res.json()]
        assert totals == sorted(totals, reverse=True)

        res = client.get("/api/invoices/", params={"sort": "total", "order": "asc"})
        totals = [i["total"] for i in res.json()]
        assert totals == sorted(totals)

        # sort by vendor A-Z.
        res = client.get("/api/invoices/", params={"sort": "vendor", "order": "asc"})
        vendors = [i["vendor"] for i in res.json()]
        assert vendors == sorted(vendors, key=str.lower)
    finally:
        for inv_id in ids:
            client.delete(f"/api/invoices/{inv_id}")


def test_bad_date_rejected(client):
    res = client.post("/api/invoices/", json=_payload(order_number="WW-BAD2", order_date="not-a-date"))
    assert res.status_code == 422


def test_expense_link_and_patch(client):
    exp = client.post(
        "/api/expenses/",
        json={"date": "2026-08-24", "category": "Seeds", "description": "Garlic order", "amount": 52.12},
    )
    assert exp.status_code == 201, exp.text
    exp_id = exp.json()["id"]

    res = client.post("/api/invoices/", json=_payload(order_number="WW-LINK", expense_id=exp_id))
    assert res.status_code == 201, res.text
    inv_id = res.json()["id"]
    assert res.json()["expense_id"] == exp_id

    # Bad expense id -> 422, not 500.
    res = client.post("/api/invoices/", json=_payload(order_number="WW-LINK2", expense_id=999999))
    assert res.status_code == 422

    # PATCH the total.
    res = client.patch(f"/api/invoices/{inv_id}", json={"total": 55.00})
    assert res.status_code == 200
    assert res.json()["total"] == 55.00

    # Clean up: the shared test DB persists across modules, so remove the
    # invoice (first — FK) and the expense we created.
    res = client.delete(f"/api/invoices/{inv_id}")
    assert res.status_code == 204
    res = client.delete(f"/api/expenses/{exp_id}")
    assert res.status_code == 204


def _pdf_bytes():
    return b"%PDF-1.4\n1 0 obj<</>>endobj\ntrailer<</Root 1 0 R>>\n"


def test_pdf_upload_and_delete(client):
    res = client.post("/api/invoices/", json=_payload(order_number="WW-PDF"))
    inv_id = res.json()["id"]

    files = {"file": ("invoice.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    res = client.post(f"/api/invoices/{inv_id}/pdf", files=files)
    assert res.status_code == 200, res.text
    pdf_path = res.json()["pdf_path"]
    assert pdf_path and pdf_path.endswith(".pdf")

    # Non-PDF rejected.
    files = {"file": ("evil.txt", io.BytesIO(b"not a pdf at all"), "text/plain")}
    res = client.post(f"/api/invoices/{inv_id}/pdf", files=files)
    assert res.status_code == 415

    # Deleting the invoice removes the file too.
    from app.database import UPLOAD_DIR

    on_disk = UPLOAD_DIR / pdf_path[len("/uploads/"):]
    assert on_disk.is_file()
    res = client.delete(f"/api/invoices/{inv_id}")
    assert res.status_code == 204
    assert not on_disk.exists()


def _csv(text):
    return {"file": ("data.csv", io.BytesIO(text.encode("utf-8-sig")), "text/csv")}


INVOICES_CSV = """Vendor,Order Number,Order Date,Total,Items,Notes
Seed Savers,SO1114706,2026-03-10,38.50,Tomato + pepper seeds,
247Garden,247-9981,2026-02-20,64.99,Grow bags,
"""


def test_csv_import_idempotent(client):
    data = {"entity": "invoices", "assignments": json.dumps({})}
    res = client.post("/api/import/run", data=data, files=_csv(INVOICES_CSV))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["imported"] == 2, body

    # Re-run: both rows skip, no dupes.
    res = client.post("/api/import/run", data=data, files=_csv(INVOICES_CSV))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["imported"] == 0, body
    assert body["skipped"] == 2, body

    res = client.get("/api/invoices/", params={"vendor": "Seed Savers"})
    assert any(i["order_number"] == "SO1114706" and i["source"] == "csv" for i in res.json())

    # Clean up the imported invoices (and their auto-created expenses) so the
    # shared test DB stays tidy for other modules' count assertions.
    for order_no in ("SO1114706", "247-9981"):
        inv = next(i for i in client.get("/api/invoices/").json()
                   if i["order_number"] == order_no)
        res = client.delete(f"/api/invoices/{inv['id']}")
        assert res.status_code == 204
