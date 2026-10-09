"""Structural integrity audit of Verdant's own cost records.

Runs live on every request (no email needed) and returns findings the Costs
page surfaces as an integrity badge. The email-vs-books comparison is posted
separately from the host reconciler (see /api/books/ledger) because only the
host has the mail ledger.

Severity: error > warn > info. The badge level is the worst severity present.
"""
from __future__ import annotations

import json
from collections import defaultdict

from sqlmodel import Session, select

from app.models import BookCheck, Expense, Invoice

VALID_CATEGORIES = ("Seeds", "Soil", "Fertilizer", "Tools", "Plants", "Supplies", "Other")
SEVERITY_ORDER = {"info": 0, "warn": 1, "error": 2}


def _f(sev: str, code: str, msg: str, **ctx) -> dict:
    return {"severity": sev, "code": code, "message": msg, **ctx}


def audit(session: Session) -> list[dict]:
    """Structural findings on Verdant's own invoices + expenses."""
    findings: list[dict] = []
    invoices = session.exec(select(Invoice)).all()
    expenses = session.exec(select(Expense)).all()
    exp_by_id = {e.id: e for e in expenses}

    for inv in invoices:
        if not inv.expense_id:
            findings.append(_f("warn", "INVOICE_NO_EXPENSE",
                f"Invoice {inv.id} ({inv.vendor or '?'}, ${inv.total:.2f}) has no backing expense — not counted in the books",
                invoice_id=inv.id))
        else:
            exp = exp_by_id.get(inv.expense_id)
            if exp is None:
                findings.append(_f("error", "INVOICE_DANGLING_EXPENSE",
                    f"Invoice {inv.id} links to expense {inv.expense_id}, which no longer exists",
                    invoice_id=inv.id))
            elif round(float(exp.amount or 0), 2) != round(float(inv.total or 0), 2):
                findings.append(_f("error", "INVOICE_EXPENSE_MISMATCH",
                    f"Invoice {inv.id} ({inv.vendor}) total ${inv.total:.2f} ≠ its expense ${float(exp.amount or 0):.2f}",
                    invoice_id=inv.id, expense_id=exp.id))
        if inv.source == "gmail" and not inv.email_link:
            findings.append(_f("info", "NO_EMAIL_LINK",
                f"Invoice {inv.id} ({inv.vendor}) came from email but has no link back to it",
                invoice_id=inv.id))

    for e in expenses:
        if round(float(e.amount or 0), 2) == 0:
            findings.append(_f("warn", "ZERO_EXPENSE",
                f"Expense {e.id} ({e.description or e.category}) is $0.00",
                expense_id=e.id))
        if e.category not in VALID_CATEGORIES:
            findings.append(_f("info", "BAD_CATEGORY",
                f"Expense {e.id} has unknown category {e.category!r}",
                expense_id=e.id))

    # Duplicate invoices: same vendor + order number recorded twice.
    seen: dict[tuple, list[int]] = defaultdict(list)
    for inv in invoices:
        onum = (inv.order_number or "").strip().upper()
        if onum:
            seen[((inv.vendor or "").strip().lower(), onum)].append(inv.id)
    for (vendor, onum), ids in seen.items():
        if len(ids) > 1:
            findings.append(_f("warn", "DUPLICATE_INVOICE",
                f"{len(ids)} invoices share order {onum} ({vendor}): ids {ids}",
                invoice_ids=ids))

    return findings


def load_ledger_findings(session: Session) -> tuple[list[dict], dict, str]:
    """Latest host-posted email-vs-books findings (empty when none posted)."""
    last = session.exec(select(BookCheck).order_by(BookCheck.checked_at.desc())).first()
    if not last:
        return [], {}, ""
    try:
        findings = json.loads(last.findings_json or "[]")
    except (ValueError, TypeError):
        findings = []
    try:
        summary = json.loads(last.summary_json or "{}")
    except (ValueError, TypeError):
        summary = {}
    return findings, summary, last.checked_at


def level_for(findings: list[dict], has_ledger: bool = True) -> str:
    """Badge level: worst severity present, else ok/unknown.

    Findings always win — a real problem shouldn't be hidden behind 'we
    haven't compared to email yet'. With nothing to report, the level is
    'ok' only once an email comparison has actually run, otherwise 'unknown'.
    """
    if findings:
        worst = "info"
        for f in findings:
            if SEVERITY_ORDER.get(f.get("severity", "info"), 0) > SEVERITY_ORDER.get(worst, 0):
                worst = f.get("severity", "info")
        return worst
    return "ok" if has_ledger else "unknown"
