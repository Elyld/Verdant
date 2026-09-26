"""API router for garden cost tracking."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Expense
from app.schemas import ExpenseCreate, ExpenseRead

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


def _get_or_404(session: Session, expense_id: int) -> Expense:
    expense = session.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail=f"Expense {expense_id} not found")
    return expense


@router.get("/", response_model=List[ExpenseRead])
def list_expenses(
    category: Optional[str] = Query(None, description="Filter by category"),
    session: Session = Depends(get_session),
) -> List[Expense]:
    query = session.query(Expense).order_by(Expense.date.desc())
    if category:
        query = query.filter(Expense.category == category)
    return query.all()


@router.post("/", response_model=ExpenseRead, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    session: Session = Depends(get_session),
) -> Expense:
    expense = Expense(
        date=payload.date.isoformat(),
        category=payload.category,
        description=payload.description,
        amount=payload.amount,
        notes=payload.notes,
        plant_id=payload.plant_id,
    )
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


@router.patch("/{expense_id}", response_model=ExpenseRead)
def update_expense(
    expense_id: int,
    payload: dict,
    session: Session = Depends(get_session),
) -> Expense:
    expense = _get_or_404(session, expense_id)
    for key, value in payload.items():
        if hasattr(expense, key) and key != "id":
            setattr(expense, key, value)
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


@router.delete("/{expense_id}", status_code=204)
def delete_expense(
    expense_id: int,
    session: Session = Depends(get_session),
) -> None:
    expense = _get_or_404(session, expense_id)
    session.delete(expense)
    session.commit()
