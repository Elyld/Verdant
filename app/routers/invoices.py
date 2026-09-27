"""API router for purchase invoices (seed & garden supplier receipts)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Expense, Invoice, apply_patch
from app.schemas import InvoiceCreate, InvoiceRead
from app.storage import delete_stored, save_pdf_upload

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

INVOICE_SOURCES = ("manual", "csv", "gmail")


def _check_source(source: str) -> None:
    if source not in INVOICE_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown source {source!r} (want one of: {', '.join(INVOICE_SOURCES)}).",
        )


def _get_or_404(session: Session, invoice_id: int) -> Invoice:
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
    return invoice


@router.get("/", response_model=List[InvoiceRead])
def list_invoices(
    vendor: Optional[str] = Query(None, description="Filter by vendor (substring)"),
    session: Session = Depends(get_session),
) -> List[Invoice]:
    query = session.query(Invoice).order_by(Invoice.order_date.desc())
    if vendor:
        query = query.filter(Invoice.vendor.contains(vendor))
    return query.all()


@router.post("/", response_model=InvoiceRead, status_code=201)
def create_invoice(
    payload: InvoiceCreate,
    session: Session = Depends(get_session),
) -> Invoice:
    _check_source(payload.source)
    if payload.expense_id is not None and not session.get(Expense, payload.expense_id):
        raise HTTPException(
            status_code=422, detail=f"Expense {payload.expense_id} not found"
        )
    invoice = Invoice(
        vendor=payload.vendor,
        order_date=payload.order_date.isoformat(),
        order_number=payload.order_number,
        total=payload.total,
        items_summary=payload.items_summary,
        notes=payload.notes,
        source=payload.source,
        expense_id=payload.expense_id,
    )
    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: int,
    payload: dict,
    session: Session = Depends(get_session),
) -> Invoice:
    invoice = _get_or_404(session, invoice_id)
    if "source" in payload:
        _check_source(payload["source"])
    if payload.get("expense_id") is not None and not session.get(
        Expense, payload["expense_id"]
    ):
        raise HTTPException(
            status_code=422, detail=f"Expense {payload['expense_id']} not found"
        )
    apply_patch(invoice, payload, exclude=("id", "pdf_path"))
    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return invoice


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(
    invoice_id: int,
    session: Session = Depends(get_session),
) -> None:
    invoice = _get_or_404(session, invoice_id)
    if invoice.pdf_path:
        delete_stored(invoice.pdf_path)
    session.delete(invoice)
    session.commit()


@router.post("/{invoice_id}/pdf", response_model=InvoiceRead)
async def upload_invoice_pdf(
    invoice_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Invoice:
    """Attach (or replace) the invoice's PDF. The old file is deleted only
    after the new upload succeeds, so a rejected upload never orphans the
    existing PDF."""
    invoice = _get_or_404(session, invoice_id)
    old_path = invoice.pdf_path
    invoice.pdf_path = await save_pdf_upload(file, f"invoices/{invoice.id}")
    if old_path:
        delete_stored(old_path)
    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return invoice


@router.delete("/{invoice_id}/pdf", response_model=InvoiceRead)
def remove_invoice_pdf(
    invoice_id: int,
    session: Session = Depends(get_session),
) -> Invoice:
    invoice = _get_or_404(session, invoice_id)
    if invoice.pdf_path:
        delete_stored(invoice.pdf_path)
        invoice.pdf_path = None
        session.add(invoice)
        session.commit()
        session.refresh(invoice)
    return invoice
