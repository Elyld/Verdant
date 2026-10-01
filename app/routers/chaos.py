"""🎲 Chaos garden pick API — one random experimental plant per year.

- GET  /api/chaos-pick          → this year's pick (draws one if none yet)
- POST /api/chaos-pick/reroll   → draw a new pick (old one never repeats
                                   this year); accepts {"variety": ...} to pin
- POST /api/chaos-pick/accept   → mark accepted; lands on the winter order
                                   list as a checked wishlist item
"""
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import chaos as chaos_mod
from app.database import get_session

router = APIRouter(prefix="/api/chaos-pick", tags=["chaos-pick"])


def _public(pick: Dict[str, Any]) -> Dict[str, Any]:
    return {"year": pick.get("year"), "variety": pick.get("variety"),
            "pitch": pick.get("pitch", ""), "kind": pick.get("kind", ""),
            "picked_at": pick.get("picked_at", ""),
            "accepted": bool(pick.get("accepted")),
            "rerolls": len(pick.get("rerolled") or [])}


@router.get("")
def get_chaos_pick(session: Session = Depends(get_session)) -> Dict[str, Any]:
    return _public(chaos_mod.current_pick(session, date.today().year))


@router.post("/reroll")
def reroll_chaos_pick(payload: Optional[dict] = None,
                      session: Session = Depends(get_session)) -> Dict[str, Any]:
    payload = payload or {}
    return _public(chaos_mod.reroll(session, date.today().year,
                                   pinned=payload.get("variety")))


@router.post("/accept")
def accept_chaos_pick(session: Session = Depends(get_session)) -> Dict[str, Any]:
    return _public(chaos_mod.accept(session, date.today().year))
