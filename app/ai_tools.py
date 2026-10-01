"""Tool-calling for the garden assistant chat.

The chat endpoint runs a small agentic loop: the model may call READ tools
(executed immediately, results fed back) and WRITE tools (validated into
draft dicts the user confirms in the UI — never executed silently).

Tools are described to the model with plain JSON schemas; keep the list
short and the descriptions concrete so small models follow them.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Optional

from sqlmodel import Session, select

from app.models import (
    Container,
    FertilizationLog,
    Harvest,
    ObservationLog,
    Plant,
    Planting,
    SeedPacket,
    WateringLog,
)


# ---------------------------------------------------------------------------
# Tool catalogue (sent to the model)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "plant_care_history",
        "description": "When a plant was last watered, fertilized (with what product), "
                       "and harvested (how many), plus its 3 most recent notes.",
        "parameters": {"plant": "plant name, e.g. 'Cherokee Purple' or 'tomatoes'"},
        "required": ["plant"],
    },
    {
        "name": "search_notes",
        "description": "Search observation/note text across the journal. "
                       "Use for 'what did I notice about…', pest history, etc.",
        "parameters": {"query": "words to search for", "plant": "optional plant name filter"},
        "required": ["query"],
    },
    {
        "name": "seed_stash",
        "description": "List seed packets in the stash, optionally filtered by a word "
                       "(variety, species, or vendor).",
        "parameters": {"query": "optional filter word"},
        "required": [],
    },
    {
        "name": "planner_overview",
        "description": "Containers and what's planted in each this season.",
        "parameters": {},
        "required": [],
    },
    {
        "name": "reminders",
        "description": "Care reminders currently due or overdue.",
        "parameters": {},
        "required": [],
    },
    {
        "name": "log_watering",
        "description": "Draft a watering log entry for a plant (user confirms before saving).",
        "parameters": {"plant": "plant name", "notes": "optional note"},
        "required": ["plant"],
    },
    {
        "name": "log_fertilization",
        "description": "Draft a feeding log entry (user confirms before saving).",
        "parameters": {"plant": "plant name", "product": "fertilizer product name",
                       "amount": "optional amount number", "unit": "optional amount unit",
                       "notes": "optional note"},
        "required": ["plant", "product"],
    },
    {
        "name": "log_harvest",
        "description": "Draft a harvest entry (user confirms before saving).",
        "parameters": {"plant": "plant name", "quantity": "how many",
                       "notes": "optional note"},
        "required": ["plant", "quantity"],
    },
    {
        "name": "log_observation",
        "description": "Draft an observation/note for a plant (user confirms before saving).",
        "parameters": {"plant": "plant name", "notes": "what was noticed"},
        "required": ["plant", "notes"],
    },
    {
        "name": "log_pest",
        "description": "Draft a pest sighting (user confirms before saving).",
        "parameters": {"plant": "plant name", "pest_name": "pest name, e.g. 'aphids'",
                       "notes": "optional note"},
        "required": ["plant", "pest_name"],
    },
    {
        "name": "add_seed_packet",
        "description": "Draft adding a seed packet to the stash (user confirms before saving).",
        "parameters": {"variety": "variety name", "species": "species, e.g. 'Tomato'",
                       "vendor": "optional vendor name", "year": "optional year acquired",
                       "quantity": "optional seed count", "notes": "optional note"},
        "required": ["variety"],
    },
    {
        "name": "update_plant",
        "description": "Draft changing a plant's status, e.g. mark it 'Harvested' or 'Done' "
                       "(user confirms before saving).",
        "parameters": {"plant": "plant name",
                       "status": "new status: Growing, Harvested, Done, or Planned"},
        "required": ["plant", "status"],
    },
    {
        "name": "move_planting",
        "description": "Draft moving a plant to a different planner container "
                       "(user confirms before saving).",
        "parameters": {"plant": "plant name", "to_container": "destination container name"},
        "required": ["plant", "to_container"],
    },
]

READ_TOOLS = {"plant_care_history", "search_notes", "seed_stash",
              "planner_overview", "reminders"}

WRITE_TOOL_ACTIONS = {
    "log_watering": "water",
    "log_fertilization": "fertilize",
    "log_harvest": "harvest",
    "log_observation": "observe",
    "log_pest": "pest",
    "add_seed_packet": "seed",
    "update_plant": "plant_status",
    "move_planting": "plant_move",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match_plant(session: Session, name: str) -> Optional[Plant]:
    """Fuzzy plant match, same spirit as the interpret flow."""
    from app.routers.ai_log import _plant_names

    key = (name or "").strip().lower()
    if not key:
        return None
    names = _plant_names(session)  # list[str]
    lowered = {n.lower(): n for n in names}
    if key in lowered:
        hit = lowered[key]
    else:
        hit = next((n for n in names if key in n.lower() or n.lower() in key), None)
    if hit is not None:
        return session.exec(select(Plant).where(Plant.variety_name == hit)).first()
    # species fallback: "tomatoes" -> a Tomato plant
    for p in session.exec(select(Plant)).all():
        sp = (p.species_type or "").strip().lower()
        if sp and key in (sp, sp + "s", sp + "es"):
            return p
    return None


def _plant_line(p: Plant) -> dict:
    return {"id": p.id, "name": p.variety_name, "species": p.species_type,
            "status": p.status}


# ---------------------------------------------------------------------------
# Read tools — executed immediately, results go back to the model
# ---------------------------------------------------------------------------

def _t_plant_care_history(session: Session, args: dict) -> dict:
    p = _match_plant(session, args.get("plant", ""))
    if not p:
        return {"error": f"No plant matching '{args.get('plant')}'."}
    w = session.exec(select(WateringLog).where(WateringLog.plant_id == p.id)
                     .order_by(WateringLog.date.desc())).first()
    f = session.exec(select(FertilizationLog).where(FertilizationLog.plant_id == p.id)
                     .order_by(FertilizationLog.date.desc())).first()
    h = session.exec(select(Harvest).where(Harvest.plant_id == p.id)
                     .order_by(Harvest.date.desc())).first()
    notes = session.exec(select(ObservationLog).where(ObservationLog.plant_id == p.id)
                         .order_by(ObservationLog.date.desc()).limit(3)).all()
    return {
        "plant": _plant_line(p),
        "last_watered": w.date if w else None,
        "last_fertilized": {"date": f.date, "product": f.fertilizer_name,
                            "amount": f.amount_used} if f else None,
        "last_harvest": {"date": h.date, "quantity": h.quantity,
                         "notes": h.notes} if h else None,
        "recent_notes": [{"date": n.date, "notes": n.notes} for n in notes],
    }


def _t_search_notes(session: Session, args: dict) -> dict:
    q = (args.get("query") or "").strip().lower()
    plant_filter = (args.get("plant") or "").strip().lower()
    if not q:
        return {"error": "query is required."}
    rows = session.exec(select(ObservationLog)
                        .order_by(ObservationLog.date.desc()).limit(200)).all()
    hits = []
    for n in rows:
        text = f"{n.plant_name} {n.notes or ''}".lower()
        if q in text and (not plant_filter or plant_filter in text):
            hits.append({"date": n.date, "plant": n.plant_name,
                         "notes": (n.notes or "")[:200]})
        if len(hits) >= 10:
            break
    return {"matches": hits}


def _t_seed_stash(session: Session, args: dict) -> dict:
    q = (args.get("query") or "").strip().lower()
    rows = session.exec(select(SeedPacket).order_by(SeedPacket.variety_name)).all()
    out = []
    for sp in rows:
        text = f"{sp.variety_name} {sp.species_type} {sp.vendor_name or ''}".lower()
        if q and q not in text:
            continue
        out.append({"variety": sp.variety_name, "species": sp.species_type,
                    "vendor": sp.vendor_name or None, "year": sp.year_acquired,
                    "seeds": sp.seed_count})
        if len(out) >= 30:
            break
    return {"packets": out}


def _t_planner_overview(session: Session, args: dict) -> dict:
    year = Date.today().year
    containers = session.exec(select(Container)
                              .where(Container.season_year == year)
                              .order_by(Container.name)).all()
    out = []
    for c in containers:
        plantings = session.exec(select(Planting)
                                 .where(Planting.container_id == c.id,
                                        Planting.season_year == year)).all()
        out.append({"container": c.name, "kind": c.kind,
                    "plants": [pl.plant.variety_name for pl in plantings if pl.plant]})
    return {"season_year": year, "containers": out}


def _t_reminders(session: Session, args: dict) -> dict:
    from app.routers.plants import plant_reminders

    due = [r for r in plant_reminders(session) if r.status in ("overdue", "due")]
    return {"due": [{"action": r.kind, "plant": r.plant_name, "status": r.status,
                     "days_overdue": -r.days_until_due if (r.days_until_due or 0) < 0 else 0}
                    for r in due[:10]]}


_READ_EXEC = {
    "plant_care_history": _t_plant_care_history,
    "search_notes": _t_search_notes,
    "seed_stash": _t_seed_stash,
    "planner_overview": _t_planner_overview,
    "reminders": _t_reminders,
}


def execute_read(session: Session, name: str, args: dict) -> dict:
    fn = _READ_EXEC.get(name)
    if not fn:
        return {"error": f"Unknown tool '{name}'."}
    try:
        return fn(session, args or {})
    except Exception as e:  # never break the loop on a tool error
        return {"error": f"{name} failed: {e}"}


# ---------------------------------------------------------------------------
# Write tools — validated into drafts the user confirms in the UI
# ---------------------------------------------------------------------------

def build_write_draft(session: Session, name: str, args: dict) -> Optional[dict]:
    """Turn a write tool call into a cleaned draft dict (or None if invalid)."""
    from app.routers.ai_log import _clean_draft

    args = args or {}
    action = WRITE_TOOL_ACTIONS.get(name)
    if not action:
        return None

    if action in ("water", "fertilize", "harvest", "observe", "pest"):
        raw = {
            "action": action,
            "plant": args.get("plant"),
            "amount": args.get("quantity") if action == "harvest" else args.get("amount"),
            "unit": args.get("unit"),
            "detail": (args.get("product") if action == "fertilize"
                       else args.get("pest_name") if action == "pest" else None),
            "notes": args.get("notes"),
        }
        return _clean_draft(raw, __plant_names(session))

    if action == "seed":
        variety = (args.get("variety") or "").strip()
        if not variety:
            return None
        detail_bits = [b for b in (args.get("species"), args.get("vendor")) if b]
        if args.get("year"):
            detail_bits.append(str(args.get("year")))
        qty = args.get("quantity")
        try:
            qty = float(qty) if qty is not None else None
        except (TypeError, ValueError):
            qty = None
        return {"action": "seed", "plant_id": None, "plant_name": variety,
                "amount": qty, "unit": "seeds" if qty else None,
                "detail": " · ".join(detail_bits) or None,
                "notes": args.get("notes"),
                "seed_species": (args.get("species") or "").strip() or None,
                "seed_vendor": (args.get("vendor") or "").strip() or None,
                "seed_year": str(args.get("year") or "").strip() or None}

    if action == "plant_status":
        p = _match_plant(session, args.get("plant", ""))
        status = (args.get("status") or "").strip().capitalize()
        if not p or status not in ("Growing", "Harvested", "Done", "Planned"):
            return None
        return {"action": "plant_status", "plant_id": p.id,
                "plant_name": p.variety_name, "amount": None, "unit": None,
                "detail": f"→ {status}", "notes": None}

    if action == "plant_move":
        p = _match_plant(session, args.get("plant", ""))
        want = (args.get("to_container") or "").strip().lower()
        if not p or not want:
            return None
        year = Date.today().year
        dest = None
        for c in session.exec(select(Container)
                              .where(Container.season_year == year)).all():
            if want in (c.name or "").lower():
                dest = c
                break
        if not dest:
            return None
        cur = session.exec(select(Planting)
                           .where(Planting.plant_id == p.id,
                                  Planting.season_year == year)).first()
        cur_name = cur.container.name if cur and cur.container else "nowhere"
        return {"action": "plant_move", "plant_id": p.id,
                "plant_name": p.variety_name, "amount": None, "unit": None,
                "detail": f"{cur_name} → {dest.name}", "notes": None,
                "to_container_id": dest.id,
                "planting_id": cur.id if cur else None}

    return None


def __plant_names(session: Session):
    from app.routers.ai_log import _plant_names

    return _plant_names(session)
