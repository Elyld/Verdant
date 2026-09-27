"""API router for purchase invoices (seed & garden supplier receipts)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from sqlmodel import select

from app.database import get_session
from app.models import Expense, Invoice, InvoiceSeedPacket, SeedPacket, apply_patch
from app.packet_match import suggest_packets
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
    # Drop packet links explicitly as well as via ON DELETE CASCADE, so the
    # cleanup holds even where the connection didn't enable FK enforcement.
    for link in session.exec(
        select(InvoiceSeedPacket).where(InvoiceSeedPacket.invoice_id == invoice_id)
    ).all():
        session.delete(link)
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


# ------------------------- seed packet links ------------------------- #

def _packet_or_404(session: Session, packet_id: int) -> SeedPacket:
    packet = session.get(SeedPacket, packet_id)
    if not packet:
        raise HTTPException(status_code=404, detail=f"Seed packet {packet_id} not found")
    return packet


def _packet_dict(packet: SeedPacket) -> dict:
    return {
        "id": packet.id,
        "variety_name": packet.variety_name,
        "vendor_name": packet.vendor_name or "",
    }


@router.get("/{invoice_id}/packets")
def list_invoice_packets(
    invoice_id: int,
    session: Session = Depends(get_session),
) -> List[dict]:
    _get_or_404(session, invoice_id)
    links = session.exec(
        select(InvoiceSeedPacket).where(InvoiceSeedPacket.invoice_id == invoice_id)
    ).all()
    packets = [session.get(SeedPacket, link.seed_packet_id) for link in links]
    return [_packet_dict(p) for p in packets if p is not None]


@router.post("/{invoice_id}/packets")
def attach_invoice_packet(
    invoice_id: int,
    payload: dict,
    session: Session = Depends(get_session),
) -> dict:
    """Link a seed packet to an invoice. Re-attaching is a no-op."""
    _get_or_404(session, invoice_id)
    packet_id = payload.get("seed_packet_id")
    packet = _packet_or_404(session, packet_id) if packet_id else None
    if packet is None:
        raise HTTPException(status_code=422, detail="seed_packet_id is required and must exist")
    existing = session.get(InvoiceSeedPacket, (invoice_id, packet.id))
    if existing is None:
        session.add(InvoiceSeedPacket(invoice_id=invoice_id, seed_packet_id=packet.id))
        session.commit()
    return _packet_dict(packet)


@router.delete("/{invoice_id}/packets/{packet_id}", status_code=204)
def detach_invoice_packet(
    invoice_id: int,
    packet_id: int,
    session: Session = Depends(get_session),
) -> None:
    _get_or_404(session, invoice_id)
    link = session.get(InvoiceSeedPacket, (invoice_id, packet_id))
    if link is None:
        raise HTTPException(status_code=404, detail="That packet is not linked to this invoice")
    session.delete(link)
    session.commit()


@router.get("/{invoice_id}/packet-suggestions")
def invoice_packet_suggestions(
    invoice_id: int,
    session: Session = Depends(get_session),
) -> List[dict]:
    """Heuristic packet matches for the invoice's items text.

    Already-linked packets are excluded; the UI lets the user confirm
    before anything is attached.
    """
    invoice = _get_or_404(session, invoice_id)
    linked_ids = frozenset(
        link.seed_packet_id
        for link in session.exec(
            select(InvoiceSeedPacket).where(InvoiceSeedPacket.invoice_id == invoice_id)
        ).all()
    )
    packets = session.exec(select(SeedPacket).order_by(SeedPacket.variety_name)).all()
    return suggest_packets(invoice.items_summary or "", packets, exclude_ids=linked_ids)
