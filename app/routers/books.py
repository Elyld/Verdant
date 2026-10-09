"""Books integrity API: structural audit + host reconciliation ingest.

  GET  /api/books/check    latest integrity report (structural + ledger)
  POST /api/books/ledger   ingest the host reconciler's email-vs-books findings
  GET  /api/books/ledger   latest posted ledger findings
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.books_audit import audit, level_for, load_ledger_findings
from app.database import get_session
from app.models import BookCheck

router = APIRouter(prefix="/api/books", tags=["books"])

MAX_FINDINGS = 500


class FindingIn(BaseModel):
    severity: str = "info"  # error | warn | info
    code: str = ""
    message: str = ""


class LedgerPush(BaseModel):
    checked_at: Optional[str] = None
    source: str = "host"
    summary: dict = Field(default_factory=dict)
    findings: List[dict] = Field(default_factory=list)


def _counts(findings: list[dict]) -> dict:
    c = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "info")
        c[sev] = c.get(sev, 0) + 1
    return c


@router.get("/check")
def get_check(session: Session = Depends(get_session)) -> dict:
    """One integrity report the Costs page renders as a badge + detail list."""
    import json

    structural = audit(session)
    ledger, summary, checked_at = load_ledger_findings(session)
    allf = structural + ledger
    return {
        "level": level_for(allf, has_ledger=bool(checked_at)),
        "counts": _counts(allf),
        "structural": structural,
        "ledger": ledger,
        "ledger_summary": summary,
        "ledger_checked_at": checked_at,
    }


@router.post("/ledger")
def post_ledger(payload: LedgerPush, session: Session = Depends(get_session)) -> dict:
    """Store the latest email-vs-books reconciliation (posted by the host)."""
    import json

    checked_at = payload.checked_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = BookCheck(
        checked_at=checked_at,
        source=(payload.source or "host")[:32],
        level=level_for(payload.findings, has_ledger=True),
        summary_json=json.dumps(payload.summary)[:20000],
        findings_json=json.dumps(payload.findings[:MAX_FINDINGS])[:200000],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {"id": row.id, "checked_at": row.checked_at, "level": row.level}


@router.get("/ledger")
def get_ledger(session: Session = Depends(get_session)) -> dict:
    findings, summary, checked_at = load_ledger_findings(session)
    return {
        "checked_at": checked_at,
        "summary": summary,
        "findings": findings,
        "counts": _counts(findings),
    }
