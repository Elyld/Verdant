"""Winter seed-order assistant: one assembled view for ordering season.

Combines, per variety:
- the stash (seed packets): how old each packet is and its "grow again?" rating,
- last year's seed spend grouped by vendor (from invoices),
- the wishlist, each row with the last vendor/date the variety was ordered
  (resolved from invoices), plus the tick-for-order checkboxes.

No new state lives here: ratings are columns on SeedPacket, the wishlist is
its own table, and invoices are the source of truth for spend and history.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlmodel import select

from app.database import get_session
from app.models import Invoice, InvoiceSeedPacket, SeedPacket, WishlistItem
from app.packet_match import parse_item_names

router = APIRouter(prefix="/api/order-assistant", tags=["order-assistant"])


def _last_order_lookup(session: Session) -> Dict[str, Dict[str, Any]]:
    """Most recent invoice per variety name (lowercased), as
    ``{variety: {"vendor": ..., "order_date": ..., "invoice_id": ...}}``.

    Explicitly linked packets (invoice_seed_packets) are authoritative;
    invoices whose items_summary merely mentions the variety name fill the
    gaps (covers wishlist varieties that have no packet yet). Invoices are
    scanned most-recent-first, so the first hit per variety wins.
    """
    invoices = session.exec(select(Invoice).order_by(Invoice.order_date.desc())).all()
    links = session.exec(select(InvoiceSeedPacket)).all()
    packet_ids_by_invoice: Dict[int, List[int]] = {}
    for link in links:
        packet_ids_by_invoice.setdefault(link.invoice_id, []).append(link.seed_packet_id)
    packets = {p.id: p for p in session.exec(select(SeedPacket)).all()}
    wishlist_names = [
        (w.variety_name or "").strip().lower()
        for w in session.exec(select(WishlistItem)).all()
    ]
    candidates = {
        (p.variety_name or "").strip().lower() for p in packets.values()
    } | {name for name in wishlist_names if name}

    best: Dict[str, Dict[str, Any]] = {}
    for inv in invoices:
        order_date = inv.order_date or ""
        entry = {"vendor": inv.vendor or "", "order_date": order_date, "invoice_id": inv.id}
        seen_here: set = set()
        # 1) Explicitly linked packets.
        for pid in packet_ids_by_invoice.get(inv.id, []):
            packet = packets.get(pid)
            key = (packet.variety_name if packet else "") or ""
            key = key.strip().lower()
            if key and key not in best:
                best[key] = entry
                seen_here.add(key)
        # 2) Items-summary text mentions (substring either way, both lowered).
        for item in parse_item_names(inv.items_summary or ""):
            lowered = item.lower()
            if not lowered:
                continue
            for key in candidates:
                if key and key not in best and key not in seen_here and (
                    key in lowered or lowered in key
                ):
                    best[key] = entry
                    seen_here.add(key)
    return best


@router.get("/")
def order_assistant(session: Session = Depends(get_session)) -> Dict[str, Any]:
    today = date.today()
    last_year = today.year - 1

    packets = session.exec(
        select(SeedPacket).order_by(SeedPacket.variety_name)
    ).all()
    wishlist = session.exec(select(WishlistItem).order_by(WishlistItem.id)).all()
    last_orders = _last_order_lookup(session)

    packet_rows = []
    for p in packets:
        age = (today.year - p.year_acquired) if p.year_acquired else None
        packet_rows.append(
            {
                "id": p.id,
                "variety_name": p.variety_name,
                "category": p.category or "",
                "vendor_name": p.vendor_name or "",
                "year_acquired": p.year_acquired,
                "stash_age_years": age,
                "grow_again": p.grow_again or "",
                "quantity": p.quantity or "",
                "seed_count": p.seed_count,
                "last_order": last_orders.get((p.variety_name or "").strip().lower()),
            }
        )

    # Last year's seed spend by vendor, from invoices.
    spend: Dict[str, Dict[str, Any]] = {}
    for inv in session.exec(select(Invoice)).all():
        if not (inv.order_date or "").startswith(str(last_year)):
            continue
        vendor = (inv.vendor or "").strip() or "Unknown vendor"
        row = spend.setdefault(vendor, {"vendor": vendor, "total": 0.0, "orders": 0})
        row["total"] = round(row["total"] + (inv.total or 0.0), 2)
        row["orders"] += 1
    vendor_spend = sorted(spend.values(), key=lambda r: -r["total"])

    wishlist_rows = [
        {
            "id": w.id,
            "variety_name": w.variety_name,
            "vendor_name": w.vendor_name or "",
            "notes": w.notes or "",
            "checked": bool(w.checked),
            "date_added": w.date_added or "",
            "last_order": last_orders.get((w.variety_name or "").strip().lower()),
        }
        for w in wishlist
    ]

    return {
        "generated_at": today.isoformat(),
        "last_year": last_year,
        "packets": packet_rows,
        "vendor_spend": vendor_spend,
        "wishlist": wishlist_rows,
    }
