"""Books integrity tests: structural audit, level, and ledger ingest.

Run with:  pytest -q
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="books-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.books_audit import level_for  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import BookCheck, Expense, Invoice  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    """Remove rows this module creates.

    The suite shares one test database (GARDEN_DATA_DIR is set with
    setdefault), so rows left behind here would skew later tests that count
    or total expenses. Delete only what we made, by marker.
    """
    yield
    with Session(engine) as s:
        for inv in s.exec(select(Invoice)).all():
            if inv.vendor in ("Ghost Co", "Mismatch Co", "Dup Co"):
                s.delete(inv)
        for e in s.exec(select(Expense)).all():
            if e.description == "x":
                s.delete(e)
        for b in s.exec(select(BookCheck)).all():
            s.delete(b)
        s.commit()


def test_level_for_ordering():
    assert level_for([]) == "ok"
    assert level_for([{"severity": "info"}]) == "info"
    assert level_for([{"severity": "info"}, {"severity": "warn"}]) == "warn"
    assert level_for([{"severity": "warn"}, {"severity": "error"}]) == "error"
    assert level_for([], has_ledger=False) == "unknown"


def test_check_empty_is_unknown_before_ledger(client):
    # Fresh DB: no structural findings, and no email comparison posted yet —
    # honest level is "unknown", not a false "ok".
    r = client.get("/api/books/check")
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == "unknown"
    assert body["structural"] == []
    assert body["ledger"] == []


def test_missing_expense_flagged(client):
    with Session(engine) as s:
        s.add(Invoice(vendor="Ghost Co", order_date="2026-01-01", order_number="G1", total=10.0, source="manual"))
        s.commit()
    r = client.get("/api/books/check").json()
    assert any(f["code"] == "INVOICE_NO_EXPENSE" and f["severity"] == "warn" for f in r["structural"])


def test_amount_mismatch_is_error(client):
    with Session(engine) as s:
        exp = Expense(date="2026-01-02", category="Seeds", description="x", amount=5.0)
        s.add(exp)
        s.commit()
        s.refresh(exp)
        s.add(Invoice(vendor="Mismatch Co", order_date="2026-01-02", order_number="M1", total=9.0, expense_id=exp.id))
        s.commit()
    r = client.get("/api/books/check").json()
    assert any(f["code"] == "INVOICE_EXPENSE_MISMATCH" and f["severity"] == "error" for f in r["structural"])
    assert r["level"] == "error"


def test_duplicate_invoice_flagged(client):
    with Session(engine) as s:
        for _ in range(2):
            s.add(Invoice(vendor="Dup Co", order_date="2026-02-01", order_number="DUP1", total=1.0))
        s.commit()
    r = client.get("/api/books/check").json()
    assert any(f["code"] == "DUPLICATE_INVOICE" for f in r["structural"])


def test_ledger_push_and_read(client):
    payload = {
        "source": "host",
        "summary": {"gap_vs_ledger": 705.82},
        "findings": [{"severity": "error", "code": "MISSING_FROM_VERDANT",
                      "message": "Home Depot $596.94 missing"}],
    }
    p = client.post("/api/books/ledger", json=payload)
    assert p.status_code == 200
    assert p.json()["level"] == "error"

    g = client.get("/api/books/ledger").json()
    assert g["findings"][0]["code"] == "MISSING_FROM_VERDANT"
    assert g["summary"]["gap_vs_ledger"] == 705.82

    chk = client.get("/api/books/check").json()
    assert any(f["code"] == "MISSING_FROM_VERDANT" for f in chk["ledger"])
    assert chk["counts"]["error"] >= 1
