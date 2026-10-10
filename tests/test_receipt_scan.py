"""Receipt photo scanning: extraction sanitizing + /scan endpoint validation.

Run with:  pytest -q
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="receipt-scan-test-"))
os.environ.setdefault("GARDEN_DATA_DIR", str(TMP / "data"))
os.environ.setdefault("GARDEN_UPLOAD_DIR", str(TMP / "uploads"))

from fastapi.testclient import TestClient  # noqa: E402

from app import llm as llm_mod  # noqa: E402
from app import receipt_scan  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def _png():
    # Minimal valid PNG header; the model is mocked so pixels don't matter.
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# --- _sanitize -------------------------------------------------------------

def test_sanitize_happy_path():
    out = receipt_scan._sanitize({
        "vendor": "  Territorial Seed  ",
        "order_date": "2026-10-01",
        "order_number": "WW123",
        "total": 52.126,
        "items_summary": "Garlic, tomato seeds",
        "notes": "",
        "sneaky": "dropped",
    })
    assert out == {
        "vendor": "Territorial Seed",
        "order_date": "2026-10-01",
        "order_number": "WW123",
        "total": 52.13,
        "items_summary": "Garlic, tomato seeds",
        "notes": None,
        "order_date": "2026-10-01",
    }
    assert "sneaky" not in out


def test_sanitize_garbage():
    out = receipt_scan._sanitize({
        "vendor": 123,
        "order_date": "yesterday",
        "total": "lots",
        "items_summary": None,
    })
    assert out["vendor"] == "123"
    assert out["order_date"] is None
    assert out["total"] is None
    assert out["items_summary"] is None


def test_sanitize_negative_total_rejected():
    assert receipt_scan._sanitize({"total": -5.0})["total"] is None


def test_sanitize_truncates_long_strings():
    out = receipt_scan._sanitize({"vendor": "x" * 500})
    assert len(out["vendor"]) == 120


# --- extract_receipt (mocked LLM) ------------------------------------------

def test_extract_receipt_uses_vision_model(monkeypatch):
    seen = {}

    def fake_chat(session, messages, json_mode=False, images=None):
        seen["json_mode"] = json_mode
        seen["images"] = images
        assert messages and "receipt" in messages[0]["content"].lower()
        return json.dumps({"vendor": "Ace Hardware", "total": 12.5})

    monkeypatch.setattr(llm_mod, "chat", fake_chat)
    out = receipt_scan.extract_receipt(object(), "data:image/png;base64,AAA")
    assert seen["json_mode"] is True
    assert seen["images"] == ["data:image/png;base64,AAA"]
    assert out["vendor"] == "Ace Hardware"
    assert out["total"] == 12.5


def test_extract_receipt_non_json_raises(monkeypatch):
    monkeypatch.setattr(llm_mod, "chat", lambda *a, **k: "not json {{")
    with pytest.raises(llm_mod.LLMError):
        receipt_scan.extract_receipt(object(), "data:image/png;base64,AAA")


def test_extract_receipt_llm_error_propagates(monkeypatch):
    def boom(*a, **k):
        raise llm_mod.LLMError("AI is off — enable it on the Settings page first.")
    monkeypatch.setattr(llm_mod, "chat", boom)
    with pytest.raises(llm_mod.LLMError, match="Settings page"):
        receipt_scan.extract_receipt(object(), "data:image/png;base64,AAA")


# --- /scan endpoint ---------------------------------------------------------

def test_scan_rejects_non_image(client):
    res = client.post(
        "/api/invoices/scan",
        files={"file": ("r.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert res.status_code == 422


def test_scan_rejects_empty(client):
    res = client.post(
        "/api/invoices/scan",
        files={"file": ("r.png", b"", "image/png")},
    )
    assert res.status_code == 422


def test_scan_rejects_oversized(client):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (receipt_scan.SCAN_MAX_BYTES + 1)
    res = client.post(
        "/api/invoices/scan",
        files={"file": ("r.png", big, "image/png")},
    )
    assert res.status_code == 413


def test_scan_llm_failure_is_502(client, monkeypatch):
    def boom(*a, **k):
        raise llm_mod.LLMError("nope")
    monkeypatch.setattr(llm_mod, "chat", boom)
    res = client.post(
        "/api/invoices/scan",
        files={"file": ("r.png", _png(), "image/png")},
    )
    assert res.status_code == 502
    assert res.json()["detail"] == "nope"


def test_scan_success_returns_extraction(client, monkeypatch):
    monkeypatch.setattr(
        llm_mod, "chat",
        lambda *a, **k: json.dumps({
            "vendor": "Menards", "order_date": "2026-10-08",
            "order_number": None, "total": 44.19,
            "items_summary": "potting mix", "notes": None,
        }),
    )
    res = client.post(
        "/api/invoices/scan",
        files={"file": ("r.png", _png(), "image/png")},
    )
    assert res.status_code == 200, res.text
    ex = res.json()["extraction"]
    assert ex["vendor"] == "Menards"
    assert ex["total"] == 44.19
    assert ex["order_date"] == "2026-10-08"
