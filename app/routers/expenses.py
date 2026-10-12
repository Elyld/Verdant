"""API router for garden cost tracking."""
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlmodel import select

from app.database import get_session
from app.models import Expense, ExpenseSeedPacket, Invoice, SeedPacket, apply_patch
from app.packet_match import suggest_packets
from app.schemas import ExpenseCreate, ExpenseRead

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

# Must match the category dropdown on the /costs page.
EXPENSE_CATEGORIES = ("Seeds", "Soil", "Fertilizer", "Tools", "Plants", "Supplies", "Other")


def _check_category(category: str) -> None:
    if category not in EXPENSE_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown category {category!r} (want one of: {', '.join(EXPENSE_CATEGORIES)}).",
        )


def _get_or_404(session: Session, expense_id: int) -> Expense:
    expense = session.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail=f"Expense {expense_id} not found")
    return expense


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
    _check_category(payload.category)
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
    if "category" in payload:
        _check_category(payload["category"])
    apply_patch(expense, payload)
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
    # Unlink any invoices pointing at this expense first: invoices.expense_id
    # has no ON DELETE action and FKs are enforced, so the delete would 500.
    # The invoices themselves are kept; they just become unlinked.
    for inv in session.query(Invoice).filter(Invoice.expense_id == expense_id).all():
        inv.expense_id = None
        inv.expense_auto_created = False
        session.add(inv)
    # Drop packet links explicitly as well as via ON DELETE CASCADE, so the
    # cleanup holds even where the connection didn't enable FK enforcement.
    for link in session.exec(
        select(ExpenseSeedPacket).where(ExpenseSeedPacket.expense_id == expense_id)
    ).all():
        session.delete(link)
    session.delete(expense)
    session.commit()


# ------------------------- seed packet links ------------------------- #

# NOTE: static sub-paths must be registered BEFORE "/{expense_id}/packets",
# or FastAPI will try to parse them as an expense id.


@router.get("/packet-links")
def all_expense_packet_links(session: Session = Depends(get_session)) -> Dict[int, List[dict]]:
    """Every expense -> linked seed packets in ONE query.

    The Costs page used to fetch /{id}/packets per row (hundreds of
    requests); this bulk endpoint replaces that storm with a single call.
    """
    links = session.exec(select(ExpenseSeedPacket)).all()
    packet_ids = {link.seed_packet_id for link in links}
    packets = (
        {p.id: p for p in session.exec(select(SeedPacket).where(SeedPacket.id.in_(packet_ids))).all()}
        if packet_ids
        else {}
    )
    out: Dict[int, List[dict]] = {}
    for link in links:
        packet = packets.get(link.seed_packet_id)
        if packet is not None:
            out.setdefault(link.expense_id, []).append(_packet_dict(packet))
    return out


@router.post("/packet-suggestions-bulk")
def bulk_expense_packet_suggestions(
    payload: dict, session: Session = Depends(get_session)
) -> Dict[int, List[dict]]:
    """Heuristic packet suggestions for many expenses in ONE call.

    payload: {"texts": {"<expense_id>": "<description + notes>"}}.
    Same ranking as GET /{id}/packet-suggestions (top 3 per row, already-
    linked packets excluded); replaces the per-row suggestion storm on the
    Costs page. The UI only ever shows the first 3, so the server trims.
    """
    texts = payload.get("texts") or {}
    eids = []
    for key in texts:
        try:
            eids.append(int(key))
        except (TypeError, ValueError):
            continue
    linked: Dict[int, set] = {}
    if eids:
        for link in session.exec(
            select(ExpenseSeedPacket).where(ExpenseSeedPacket.expense_id.in_(eids))
        ).all():
            linked.setdefault(link.expense_id, set()).add(link.seed_packet_id)
    packets = session.exec(select(SeedPacket).order_by(SeedPacket.variety_name)).all()
    return {
        eid: suggest_packets(
            texts.get(str(eid)) or "", packets,
            exclude_ids=frozenset(linked.get(eid, ())),
        )[:3]
        for eid in eids
    }


@router.get("/{expense_id}/packets")
def list_expense_packets(
    expense_id: int,
    session: Session = Depends(get_session),
) -> List[dict]:
    _get_or_404(session, expense_id)
    links = session.exec(
        select(ExpenseSeedPacket).where(ExpenseSeedPacket.expense_id == expense_id)
    ).all()
    packet_ids = [link.seed_packet_id for link in links]
    packets = (
        {p.id: p for p in session.exec(select(SeedPacket).where(SeedPacket.id.in_(packet_ids))).all()}
        if packet_ids
        else {}
    )
    return [_packet_dict(packets[pid]) for pid in packet_ids if pid in packets]


@router.post("/{expense_id}/packets")
def attach_expense_packet(
    expense_id: int,
    payload: dict,
    session: Session = Depends(get_session),
) -> dict:
    """Link a seed packet to an expense. Re-attaching is a no-op."""
    _get_or_404(session, expense_id)
    packet_id = payload.get("seed_packet_id")
    packet = _packet_or_404(session, packet_id) if packet_id else None
    if packet is None:
        raise HTTPException(status_code=422, detail="seed_packet_id is required and must exist")
    existing = session.get(ExpenseSeedPacket, (expense_id, packet.id))
    if existing is None:
        session.add(ExpenseSeedPacket(expense_id=expense_id, seed_packet_id=packet.id))
        session.commit()
    return _packet_dict(packet)


@router.delete("/{expense_id}/packets/{packet_id}", status_code=204)
def detach_expense_packet(
    expense_id: int,
    packet_id: int,
    session: Session = Depends(get_session),
) -> None:
    _get_or_404(session, expense_id)
    link = session.get(ExpenseSeedPacket, (expense_id, packet_id))
    if link is None:
        raise HTTPException(status_code=404, detail="That packet is not linked to this expense")
    session.delete(link)
    session.commit()


@router.get("/{expense_id}/packet-suggestions")
def expense_packet_suggestions(
    expense_id: int,
    session: Session = Depends(get_session),
) -> List[dict]:
    """Heuristic packet matches for the expense's description + notes.

    Auto-created expenses carry the invoice's items summary in notes, so
    suggestions work the same as on invoices. Already-linked packets are
    excluded; the UI lets the user confirm before anything is attached.
    """
    expense = _get_or_404(session, expense_id)
    linked_ids = frozenset(
        link.seed_packet_id
        for link in session.exec(
            select(ExpenseSeedPacket).where(ExpenseSeedPacket.expense_id == expense_id)
        ).all()
    )
    text = "\n".join(t for t in (expense.description or "", expense.notes or "") if t)
    packets = session.exec(select(SeedPacket).order_by(SeedPacket.variety_name)).all()
    return suggest_packets(text, packets, exclude_ids=linked_ids)
