"""📕 Yearbook PDF + 💰 true-cost verdict endpoints.

The empty-year yearbook renders a graceful "quiet year" PDF instead of a
404 — a printable keepsake either way.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Query
from fastapi import Depends
from fastapi.responses import Response
from sqlmodel import Session

from app.database import get_session
from app import true_cost as true_cost_mod
from app import yearbook as yearbook_mod

router = APIRouter(prefix="/api", tags=["yearbook"])


@router.get("/yearbook")
def download_yearbook(
    year: int = Query(default=None, description="Season year (defaults to current year)"),
    session: Session = Depends(get_session),
) -> Response:
    """The season yearbook as a PDF: title page, stats table, AI story,
    and season photos. A quiet year still renders a keepsake."""
    if year is None:
        year = Date.today().year
    stats = yearbook_mod.build_yearbook_stats(session, year)
    story = yearbook_mod.write_story(session, stats) if stats else None
    photos = yearbook_mod.yearbook_photos(session, year) if stats else []
    pdf = yearbook_mod.render_pdf(stats, story, photos)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="verdant-yearbook-{year}.pdf"'},
    )


@router.get("/true-cost", tags=["true-cost"])
def get_true_cost(
    year: int = Query(default=None, description="Season year (defaults to current year)"),
    session: Session = Depends(get_session),
) -> dict:
    """💰 True-cost verdict: $/lb homegrown vs. grocery-store estimates."""
    return true_cost_mod.true_cost_report(session, year)
