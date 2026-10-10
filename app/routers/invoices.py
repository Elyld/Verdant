"""API router for purchase invoices (seed & garden supplier receipts)."""
import base64
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from sqlmodel import select

from app import llm as llm_mod
from app.database import get_session
from app.invoice_expenses import (
    auto_create_expense,
    delete_auto_expense,
    sync_auto_expense,
)
from app.models import Expense, Invoice, InvoiceSeedPacket, SeedPacket, apply_patch
from app.packet_match import best_packet_match, suggest_packets
from app.receipt_scan import SCAN_IMAGE_TYPES, SCAN_MAX_BYTES, extract_receipt
from app.schemas import InvoiceCreate, InvoiceRead
from app.seed_extract import candidates_from_invoice
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
    q: Optional[str] = Query(
        None, description="Search vendor, order number, and items (substring)"
    ),
    source: Optional[str] = Query(
        None, description="Filter by source: manual, csv, or gmail"
    ),
    sort: str = Query("date", description="Sort key: date, vendor, or total"),
    order: str = Query("desc", description="Sort direction: asc or desc"),
    session: Session = Depends(get_session),
) -> List[Invoice]:
    if source is not None:
        _check_source(source)
    query = session.query(Invoice)
    if vendor:
        query = query.filter(Invoice.vendor.contains(vendor))
    if q:
        query = query.filter(
            (Invoice.vendor.contains(q))
            | (Invoice.order_number.contains(q))
            | (Invoice.items_summary.contains(q))
        )
    if source:
        query = query.filter(Invoice.source == source)
    sort_col = {
        "date": Invoice.order_date,
        "vendor": Invoice.vendor,
        "total": Invoice.total,
    }.get(sort, Invoice.order_date)
    # order_date is stored ISO YYYY-MM-DD so string sort == date sort.
    query = query.order_by(
        sort_col.asc() if order == "asc" else sort_col.desc()
    )
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
        email_link=payload.email_link,
        source=payload.source,
        expense_id=payload.expense_id,
    )
    session.add(invoice)
    if payload.expense_id is None:
        # No manual link: back the invoice with an auto-created expense.
        auto_create_expense(session, invoice)
    session.commit()
    session.refresh(invoice)
    return invoice


@router.post("/scan")
async def scan_receipt_photo(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    """Read a photographed paper receipt with the vision model.

    Returns {"extraction": {vendor, order_date, order_number, total,
    items_summary, notes}} — nothing is saved. The UI shows the extraction
    for review and fills the invoice form on confirmation.
    """
    ctype = (file.content_type or "").lower()
    if ctype not in SCAN_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Not a photo (want one of: {', '.join(sorted(SCAN_IMAGE_TYPES))}).",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(raw) > SCAN_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Photo is {len(raw) // 1024 // 1024} MB — keep it under "
            f"{SCAN_MAX_BYTES // 1024 // 1024} MB.",
        )
    data_uri = f"data:{ctype};base64," + base64.b64encode(raw).decode("ascii")
    try:
        extraction = extract_receipt(session, data_uri)
    except llm_mod.LLMError as exc:
        # extract_receipt only raises LLMError with user-friendly messages.
        raise HTTPException(status_code=502, detail=str(exc))
    return {"extraction": extraction}


@router.post("/{invoice_id}/create-expense", response_model=InvoiceRead)
def create_invoice_expense(
    invoice_id: int,
    session: Session = Depends(get_session),
) -> Invoice:
    """Back an existing invoice with an expense row.

    Idempotent: an invoice that already links to an expense is returned
    unchanged — this never creates a duplicate expense.
    """
    invoice = _get_or_404(session, invoice_id)
    auto_create_expense(session, invoice)
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
    prev_expense_id = invoice.expense_id
    apply_patch(invoice, payload, exclude=("id", "pdf_path"))
    if "expense_id" in payload and payload["expense_id"] != prev_expense_id:
        # The link was changed (or removed) by hand: it's manual now, and the
        # auto-created expense — if any — is left in place, never deleted here.
        invoice.expense_auto_created = False
    else:
        # Push total/date/vendor/description onto the auto-created expense.
        sync_auto_expense(session, invoice)
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
    # An auto-created expense goes with its invoice (unless another invoice
    # still links to it); a manually linked expense is left alone.
    delete_auto_expense(session, invoice)
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


@router.post("/{invoice_id}/derive-packets")
def derive_invoice_packets(
    invoice_id: int,
    payload: Optional[dict] = Body(default=None),
    session: Session = Depends(get_session),
) -> dict:
    """Grow the seed stash from this invoice's line items.

    Every seed-like line item is normalized to a variety. An item that already
    matches a packet in the stash is linked to that packet; anything new is
    created and linked to the invoice. A container/tool/supply line (pots, grow
    bags, soil) is never turned into a packet.

    ``apply`` defaults to false, returning the plan without writing — the UI
    previews it, then re-calls with ``apply: true``. Idempotent: re-running
    links the same packets and creates nothing new.
    """
    invoice = _get_or_404(session, invoice_id)
    apply = bool((payload or {}).get("apply"))
    linked_ids = {
        link.seed_packet_id
        for link in session.exec(
            select(InvoiceSeedPacket).where(InvoiceSeedPacket.invoice_id == invoice_id)
        ).all()
    }
    stash = session.exec(select(SeedPacket).order_by(SeedPacket.variety_name)).all()
    candidates = candidates_from_invoice(
        invoice.items_summary or "", invoice.vendor or "", invoice.order_date or ""
    )

    plan: List[dict] = []
    created_ids: List[int] = []
    for cand in candidates:
        match, score = best_packet_match(cand["variety_name"], stash)
        if match is not None:
            action = "already_linked" if match.id in linked_ids else "link"
            packet_id = match.id
        else:
            action = "create"
            packet_id = None
        plan.append({
            "variety_name": cand["variety_name"],
            "category": cand["category"],
            "quantity": cand["quantity"],
            "source_item": cand["source_item"],
            "action": action,
            "packet_id": packet_id,
            "match_score": round(score, 2),
        })
        if not apply or action == "already_linked":
            continue
        if packet_id is None:
            packet = SeedPacket(
                variety_name=cand["variety_name"],
                category=cand["category"],
                species_type=cand["species_type"],
                vendor_name=cand["vendor_name"],
                year_acquired=cand["year_acquired"],
                quantity=cand["quantity"],
                notes=f"From invoice #{invoice.id} — {invoice.vendor} {invoice.order_date}".strip(),
            )
            session.add(packet)
            session.flush()  # assign packet.id for the link below
            stash.append(packet)  # so later dupes in the same run link to it
            packet_id = packet.id
            created_ids.append(packet_id)
        session.add(InvoiceSeedPacket(invoice_id=invoice.id, seed_packet_id=packet_id))

    if apply:
        session.commit()

    return {
        "invoice_id": invoice.id,
        "vendor": invoice.vendor,
        "applied": apply,
        "created": created_ids,
        "plan": plan,
    }
