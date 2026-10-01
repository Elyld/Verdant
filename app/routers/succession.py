"""Succession planting API — what can still go into empty containers this season."""
from __future__ import annotations

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import succession as succession_mod
from app.database import get_session

router = APIRouter(prefix="/api/succession", tags=["succession"])


@router.get("/suggestions")
def succession_suggestions(
    year: Optional[int] = Query(None, description="Planner season year (default: current)"),
    as_of: Optional[Date] = Query(
        None, description="Preview as of a date (default: today)"
    ),
    session: Session = Depends(get_session),
) -> dict:
    return succession_mod.suggestions(session, year=year, today=as_of)
