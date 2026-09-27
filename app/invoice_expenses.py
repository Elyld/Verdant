"""Auto-create and sync the backing Expense for an invoice.

An invoice may link to the Expense row it documents. When the invoice is
created without an explicit expense link, the expense is auto-created from
the invoice's own data (total, order date, vendor, items). Auto-created
expenses are flagged on the invoice (``expense_auto_created``) so updates
and deletes can tell them apart from manually linked ones:

- PATCH on the invoice syncs amount/date/description onto the auto expense.
- DELETE of the invoice deletes the auto expense (but only if no other
  invoice links to it); manually linked expenses are never touched.
- The endpoints here are idempotent: calling twice never makes a dupe.
"""
from typing import Optional

from sqlmodel import Session, select

from app.models import Expense, Invoice

AUTO_CATEGORY = "Seeds"
NOTES_MAX = 500


def expense_description(invoice: Invoice) -> str:
    """Human-readable expense description derived from the invoice."""
    vendor = (invoice.vendor or "").strip()
    order = (invoice.order_number or "").strip()
    if vendor and order:
        return f"{vendor} — order {order}"
    return vendor or order or "Invoice"


def auto_create_expense(session: Session, invoice: Invoice) -> Expense:
    """Create the backing Expense for an invoice and link it.

    Idempotent: if the invoice already links to an existing expense, that
    expense is returned unchanged and nothing new is created. The caller
    commits; this only flushes so the new expense gets an id.
    """
    if invoice.expense_id is not None:
        existing = session.get(Expense, invoice.expense_id)
        if existing is not None:
            return existing
    notes = (invoice.items_summary or "").strip()
    if len(notes) > NOTES_MAX:
        notes = notes[: NOTES_MAX - 3].rstrip() + "..."
    expense = Expense(
        date=invoice.order_date or "",
        category=AUTO_CATEGORY,
        description=expense_description(invoice),
        amount=float(invoice.total or 0.0),
        notes=notes or None,
    )
    session.add(expense)
    session.flush()  # assign expense.id before linking
    invoice.expense_id = expense.id
    invoice.expense_auto_created = True
    session.add(invoice)
    return expense


def sync_auto_expense(session: Session, invoice: Invoice) -> Optional[Expense]:
    """Push the invoice's total/date/vendor/description onto its auto-created
    expense. Returns the expense, or None when there is nothing to sync
    (manually linked, unlinked, or the expense row is gone)."""
    if not invoice.expense_auto_created or invoice.expense_id is None:
        return None
    expense = session.get(Expense, invoice.expense_id)
    if expense is None:
        return None
    expense.amount = float(invoice.total or 0.0)
    expense.date = invoice.order_date or ""
    expense.description = expense_description(invoice)
    session.add(expense)
    return expense


def delete_auto_expense(session: Session, invoice: Invoice) -> bool:
    """Delete the invoice's auto-created expense.

    Returns True when an expense was deleted. Refuses to delete when another
    invoice still links to the same expense, so a shared link never dangles.
    The invoice's expense_id is nulled first so the invoices.expense_id
    foreign key doesn't block the delete.
    """
    if not invoice.expense_auto_created or invoice.expense_id is None:
        return False
    expense = session.get(Expense, invoice.expense_id)
    invoice.expense_id = None
    session.add(invoice)
    if expense is None:
        return False
    shared = session.exec(
        select(Invoice).where(
            Invoice.expense_id == expense.id,
            Invoice.id != invoice.id,
        )
    ).first()
    if shared is not None:
        return False
    session.delete(expense)
    return True
