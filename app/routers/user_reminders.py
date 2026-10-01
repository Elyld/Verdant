"""Dated reminders the gardener sets via the AI chat.

The chat's set_reminder tool creates a DRAFT the gardener confirms in the UI;
the UI posts here. Read-only surfaces (chat context, Discord digest) pull the
pending rows. Nothing is ever scheduled silently — every row exists because
the gardener confirmed it.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import UserReminder

router = APIRouter(prefix="/api/user-reminders", tags=["user-reminders"])


def validate_due_date(value: str) -> str:
    """Clean a YYYY-MM-DD due date. Raises 400 on bad format or past dates."""
    text = (value or "").strip()
    try:
        parsed = Date.fromisoformat(text)
    except ValueError:
        raise HTTPException(
            400, f"due_date {text!r} isn't a valid date — use YYYY-MM-DD.")
    if parsed < Date.today():
        raise HTTPException(
            400, "That date is in the past — pick today or a future date.")
    return text


class ReminderCreate(BaseModel):
    title: str
    due_date: str  # YYYY-MM-DD, today or future
    notes: Optional[str] = None


class ReminderPatch(BaseModel):
    done: Optional[bool] = None
    title: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


def _row(r: UserReminder) -> dict:
    today = Date.today().isoformat()
    return {
        "id": r.id,
        "title": r.title,
        "due_date": r.due_date,
        "notes": r.notes,
        "done": r.done,
        "overdue": (not r.done) and bool(r.due_date) and r.due_date < today,
    }


@router.get("")
def list_reminders(all: bool = False,
                   session: Session = Depends(get_session)) -> dict:
    """Pending reminders first (overdue, then by date). all=true includes done."""
    stmt = select(UserReminder).order_by(UserReminder.due_date, UserReminder.id)
    if not all:
        stmt = stmt.where(UserReminder.done == False)  # noqa: E712
    rows = session.exec(stmt).all()
    rows = sorted(rows, key=lambda r: (r.due_date >= Date.today().isoformat(),
                                      r.due_date))
    return {"reminders": [_row(r) for r in rows]}


@router.post("")
def create_reminder(payload: ReminderCreate,
                    session: Session = Depends(get_session)) -> dict:
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(400, "Give the reminder a title.")
    due = validate_due_date(payload.due_date)
    r = UserReminder(title=title[:200], due_date=due,
                     notes=(payload.notes or "").strip()[:500] or None)
    session.add(r)
    session.commit()
    session.refresh(r)
    return {"ok": True, "reminder": _row(r)}


@router.patch("/{reminder_id}")
def update_reminder(reminder_id: int, payload: ReminderPatch,
                    session: Session = Depends(get_session)) -> dict:
    r = session.get(UserReminder, reminder_id)
    if not r:
        raise HTTPException(404, "Reminder not found.")
    if payload.done is not None:
        r.done = bool(payload.done)
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(400, "Give the reminder a title.")
        r.title = title[:200]
    if payload.due_date is not None:
        r.due_date = validate_due_date(payload.due_date)
    if payload.notes is not None:
        r.notes = payload.notes.strip()[:500] or None
    session.add(r)
    session.commit()
    session.refresh(r)
    return {"ok": True, "reminder": _row(r)}


@router.delete("/{reminder_id}")
def delete_reminder(reminder_id: int,
                    session: Session = Depends(get_session)) -> dict:
    r = session.get(UserReminder, reminder_id)
    if not r:
        raise HTTPException(404, "Reminder not found.")
    session.delete(r)
    session.commit()
    return {"ok": True}
