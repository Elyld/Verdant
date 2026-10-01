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

from app import frost as frost_mod
from app import units as units_mod
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
        "name": "record_autopsy",
        "description": "Draft a plant autopsy note when a plant dies — cause of death "
                       "plus what it looked like at the end (user confirms before saving).",
        "parameters": {"plant": "plant name",
                       "cause": "cause of death, e.g. 'damping off'",
                       "notes": "optional extra detail, e.g. what it looked like at the end"},
        "required": ["plant", "cause"],
    },
    {
        "name": "move_planting",
        "description": "Draft moving a plant to a different planner container "
                       "(user confirms before saving).",
        "parameters": {"plant": "plant name", "to_container": "destination container name"},
        "required": ["plant", "to_container"],
    },
    {
        "name": "season_advice",
        "description": "Seasonal guidance for the gardener's zone: first-frost countdown, "
                       "what to plant and harvest right now, garlic planting reminder, "
                       "seed-order hints. Advisory only — makes no garden changes.",
        "parameters": {},
        "required": [],
    },
    {
        "name": "save_memory_note",
        "description": "Save a memory note for future chats — a preference or idea "
                       "the gardener wants remembered. Stored as a Garden Log note "
                       "under 'Notebook'. Creates a DRAFT the gardener confirms "
                       "before anything is saved. NOT a reminder — it cannot "
                       "schedule anything; for 'remind me…', use set_reminder.",
        "parameters": {"note": "the note text to remember",
                       "plant": "optional plant name this relates to"},
        "required": ["note"],
    },
    {
        "name": "set_reminder",
        "description": "Draft a dated reminder for the gardener (user confirms "
                       "before saving). Use when they ask to be reminded at a "
                       "time/date, e.g. 'remind me to plant carrots on Oct 12'. "
                       "This is the ONLY way to schedule a reminder — memory "
                       "notes cannot do it.",
        "parameters": {"title": "what to be reminded about, e.g. 'plant carrots'",
                       "due_date": "YYYY-MM-DD, today or a future date",
                       "notes": "optional extra detail"},
        "required": ["title", "due_date"],
    },
    {
        "name": "upcoming_reminders",
        "description": "List the gardener's pending dated reminders, overdue first. "
                       "Use for 'what did I ask to be reminded about'.",
        "parameters": {},
        "required": [],
    },
    {
        "name": "recall_notes",
        "description": "Search previously saved memory notes and journal observations. "
                       "Use when the gardener asks 'what did I note about…' or "
                       "'remember when…'.",
        "parameters": {"query": "words to search for"},
        "required": ["query"],
    },
    {
        "name": "variety_performance",
        "description": "Year-over-year harvest performance per variety: harvest counts "
                       "and total quantities from the harvest logs. "
                       "Use for 'which variety did best' questions.",
        "parameters": {"variety": "optional variety name filter"},
        "required": [],
    },
    {
        "name": "season_recap",
        "description": "Narrate a plant's season from its photos: gathers the plant's "
                       "photos across the season (matched album photos + observation "
                       "photos) and has the vision model tell the story — growth "
                       "milestones, health observations, harvest moments. "
                       "Use for 'recap my tomatoes' season' type questions.",
        "parameters": {"plant": "plant name, e.g. 'Cherokee Purple' or 'tomatoes'"},
        "required": ["plant"],
    },
    {
        "name": "this_week_last_year",
        "description": "What happened in the garden during this same week last year — "
                       "journal notes, harvests, and photos. Use for 'what did I do "
                       "this time last year' questions.",
        "parameters": {},
        "required": [],
    },
    {
        "name": "growth_check",
        "description": "Compare recent photos of one plant (last ~6 weeks) to see if "
                       "it has visibly grown or stalled, with likely causes. "
                       "Advisory only. Use for 'is my tomato still growing?'.",
        "parameters": {"plant": "plant name, e.g. 'Cherokee Purple' or 'tomatoes'"},
        "required": ["plant"],
    },
    {
        "name": "frost_gamble",
        "description": "When frost threatens tonight: one bold call — COVER the tender "
                       "plants or HARVEST NOW what's ripe. Advisory only; nothing to "
                       "run when there's no frost risk (returns empty).",
        "parameters": {},
        "required": [],
    },
    {
        "name": "true_cost",
        "description": "Was it cheaper than the grocery store? Total spend and $/lb "
                       "homegrown vs. grocery-store estimates, per variety with "
                       "fun, honest verdicts. Use for 'was it worth it' money questions.",
        "parameters": {"year": "optional season year, e.g. 2025 (defaults to current year)"},
        "required": [],
    },
    {
        "name": "chaos_pick",
        "description": "The year's 🎲 chaos pick — one random experimental plant, "
                       "always something the gardener has never grown. Use for "
                       "'what's my chaos pick'. With action='reroll', DRAFT a new "
                       "pick the gardener confirms before it replaces the current one.",
        "parameters": {"action": "optional: 'reroll' to draw a new pick (drafted for confirmation)"},
        "required": [],
    },
]

READ_TOOLS = {"plant_care_history", "search_notes", "seed_stash",
              "planner_overview", "reminders", "season_advice",
              "recall_notes", "variety_performance", "season_recap",
              "upcoming_reminders", "this_week_last_year", "growth_check",
              "frost_gamble", "true_cost", "chaos_pick"}

WRITE_TOOL_ACTIONS = {
    "log_watering": "water",
    "log_fertilization": "fertilize",
    "log_harvest": "harvest",
    "log_observation": "observe",
    "log_pest": "pest",
    "add_seed_packet": "seed",
    "update_plant": "plant_status",
    "move_planting": "plant_move",
    "save_memory_note": "note",
    "set_reminder": "reminder",
    "record_autopsy": "note",
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


def _t_season_advice(session: Session, args: dict) -> dict:
    today = Date.today()
    month = today.strftime("%B")
    zone = (frost_mod.get_setting(session, "zone") or "").strip() or "?"
    frost = None
    try:
        frost, _src, _z = frost_mod.resolve_frost(session, "first", today=today)
    except Exception:
        frost = None
    days_to_frost = (frost - today).days if frost else None

    advice = []
    if frost:
        advice.append(
            f"First frost is around {frost.strftime('%b %d')} — "
            f"{days_to_frost} day{'s' if days_to_frost != 1 else ''} out (zone {zone}).")
    else:
        advice.append(
            "No first-frost date on file — set your zone or frost date in Settings "
            "for a countdown.")
    # Garlic: user plants in late October, regardless of whether frost resolves.
    if month == "October" and days_to_frost is not None and days_to_frost <= 31:
        advice.append("Garlic goes in the ground in late October — get beds ready and "
                      "cloves planted before the ground hardens.")
    elif month == "October":
        advice.append("Garlic goes in the ground in late October — order seed garlic "
                      "now if you haven't yet.")
    else:
        advice.append("Garlic goes in the ground in late October — mark the calendar.")
    if days_to_frost is not None and days_to_frost <= 21:
        advice.append("Plant now: spinach and lettuce under row cover, or a cover crop "
                      "to rest the beds over winter.")
    else:
        advice.append("Plant now: fall greens under cover, garlic in late October, and "
                      "cover crops on empty beds.")
    advice.append("Harvest: pull the last tomatoes and peppers before frost, dig sweet "
                  "potatoes, and dry or freeze herbs for winter.")
    advice.append("Seed-order hint: check the stash for packets ~3 years or older, "
                  "or with poor germination — replace those first.")

    def _fit(s: str) -> str:
        return s if len(s) <= 140 else s[:137] + "..."

    return {
        "month": month,
        "zone": zone,
        "first_frost": frost.isoformat() if frost else None,
        "days_to_frost": days_to_frost,
        "advice": [_fit(a) for a in advice],
    }


def _t_recall_notes(session: Session, args: dict) -> dict:
    q = (args.get("query") or "").strip().lower()
    if not q:
        return {"error": "query is required."}
    rows = session.exec(select(ObservationLog)
                        .order_by(ObservationLog.date.desc()).limit(300)).all()
    memory_hits, regular_hits = [], []
    for n in rows:
        text = f"{n.plant_name} {n.notes or ''}".lower()
        if q not in text:
            continue
        entry = {"date": n.date, "plant": n.plant_name,
                 "notes": (n.notes or "")[:200],
                 "memory": (n.plant_name or "") == "Notebook"}
        (memory_hits if entry["memory"] else regular_hits).append(entry)
    return {"matches": (memory_hits + regular_hits)[:10]}


def _t_this_week_last_year(session: Session, args: dict) -> dict:
    """What happened in the garden this same week last year (read-only)."""
    import app.time_travel as time_travel_mod

    return time_travel_mod.this_week_last_year(session)


def _t_growth_check(session: Session, args: dict) -> dict:
    """Compare a plant's recent photos for visible growth (read-only)."""
    import app.stall as stall_mod

    return stall_mod.growth_check(session, args.get("plant", ""))


def _t_frost_gamble(session: Session, args: dict) -> dict:
    """One bold frost call — COVER or HARVEST NOW (read-only)."""
    import app.frost_gamble as frost_gamble_mod

    verdict = frost_gamble_mod.frost_verdict(session)
    if verdict is None:
        return {"verdict": None,
                "note": "No frost risk tonight — nothing to call."}
    return verdict


def _t_true_cost(session: Session, args: dict) -> dict:
    """Homegrown $/lb vs grocery-store estimates (read-only)."""
    import app.true_cost as true_cost_mod

    year = args.get("year")
    try:
        year = int(year) if year else Date.today().year
    except (TypeError, ValueError):
        year = Date.today().year
    return true_cost_mod.true_cost_report(session, year)


def _t_chaos_pick(session: Session, args: dict) -> dict:
    """This year's 🎲 chaos pick (read-only query path)."""
    import app.chaos as chaos_mod

    pick = chaos_mod.current_pick(session, Date.today().year)
    return {"year": pick["year"], "variety": pick["variety"],
            "pitch": pick.get("pitch", ""), "kind": pick.get("kind", ""),
            "accepted": bool(pick.get("accepted")),
            "rerolls": len(pick.get("rerolled") or [])}


def _t_season_recap(session: Session, args: dict) -> dict:
    """Narrate a plant's season from its photos (read-only)."""
    import app.season_recap as recap_mod

    p = _match_plant(session, args.get("plant", ""))
    if p is None:
        return {"error": f"No plant matched '{args.get('plant', '')}'. Name a plant from the Plants page."}
    return recap_mod.build_recap(session, p)


def _t_variety_performance(session: Session, args: dict) -> dict:
    variety_filter = (args.get("variety") or "").strip().lower()
    rows = session.exec(select(Harvest)
                        .order_by(Harvest.date.desc()).limit(2000)).all()
    per_variety: dict[str, dict] = {}
    for h in rows:
        variety = (h.plant.variety_name if h.plant else None) or "Unknown"
        if variety_filter and variety_filter not in variety.lower():
            continue
        year = (h.date or "")[:4] or "unknown"
        entry = per_variety.setdefault(variety, {})
        y = entry.setdefault(year, {"harvests": 0, "quantity": 0, "weight_oz": 0.0})
        y["harvests"] += 1
        y["quantity"] += h.quantity or 0
        oz = units_mod.to_oz(h.weight, h.weight_unit)
        if oz is not None:
            y["weight_oz"] += oz
    varieties = []
    for variety, years in per_variety.items():
        total_harvests = sum(y["harvests"] for y in years.values())
        total_quantity = sum(y["quantity"] for y in years.values())
        for y in years.values():
            y["weight_oz"] = round(y["weight_oz"], 2)
        varieties.append({"variety": variety, "years": years,
                          "total_harvests": total_harvests,
                          "total_quantity": total_quantity})
    # --- 💀 plant autopsies: death notes ride along with performance ---
    from app import autopsy as autopsy_mod

    deaths = autopsy_mod.autopsy_deaths_by_variety(session)
    if variety_filter:
        deaths = {v: d for v, d in deaths.items()
                  if variety_filter in v.lower()}
    autopsy_mod.attach_deaths(varieties, deaths)
    varieties.sort(key=lambda v: v["total_quantity"], reverse=True)
    return {"varieties": varieties[:20]}


def _parse_due_date(value: str) -> Optional[str]:
    """Validate a YYYY-MM-DD due date: correct format and not in the past.
    Returns the cleaned string, or None when invalid."""
    text = (value or "").strip()
    try:
        parsed = Date.fromisoformat(text)
    except ValueError:
        return None
    if parsed < Date.today():
        return None
    return text


def _t_upcoming_reminders(session: Session, args: dict) -> dict:
    from app.models import UserReminder

    today = Date.today().isoformat()
    rows = session.exec(
        select(UserReminder)
        .where(UserReminder.done == False)  # noqa: E712
        .order_by(UserReminder.due_date, UserReminder.id)).all()
    # Overdue first, then by date.
    rows = sorted(rows, key=lambda r: (r.due_date >= today, r.due_date))
    out = []
    for r in rows[:15]:
        days = (Date.fromisoformat(r.due_date) - Date.today()).days \
            if r.due_date else None
        out.append({"id": r.id, "title": r.title, "due_date": r.due_date,
                    "notes": r.notes,
                    "status": "overdue" if (days is not None and days < 0)
                    else "due today" if days == 0
                    else f"in {days}d" if days is not None else "unscheduled"})
    return {"reminders": out}


_READ_EXEC = {
    "plant_care_history": _t_plant_care_history,
    "search_notes": _t_search_notes,
    "seed_stash": _t_seed_stash,
    "planner_overview": _t_planner_overview,
    "reminders": _t_reminders,
    "season_advice": _t_season_advice,
    "recall_notes": _t_recall_notes,
    "variety_performance": _t_variety_performance,
    "season_recap": _t_season_recap,
    "upcoming_reminders": _t_upcoming_reminders,
    "this_week_last_year": _t_this_week_last_year,
    "growth_check": _t_growth_check,
    "frost_gamble": _t_frost_gamble,
    "true_cost": _t_true_cost,
    "chaos_pick": _t_chaos_pick,
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
    if name == "chaos_pick":
        # Reroll is a write: draft the exact candidate pick so the gardener
        # confirms it in chat before it replaces the current one.
        from app import chaos as chaos_mod

        preview = chaos_mod.preview_reroll(session, Date.today().year)
        return {"action": "chaos_reroll", "plant_name": preview["variety"],
                "notes": preview["pitch"]}
    action = WRITE_TOOL_ACTIONS.get(name)
    if not action:
        return None

    if name == "record_autopsy":
        # Autopsy rides the existing "note" draft flow (same as save_memory_note):
        # compose the note text + plant, then fall through to the note branch.
        from app import autopsy as autopsy_mod

        args = autopsy_mod.resolve_autopsy_args(session, args.get("plant"),
                                                args.get("cause"), args.get("notes"))
        if args is None:
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

    if action == "note":
        notes = (args.get("note") or "").strip()
        if not notes:
            return None
        raw = {
            "action": "note",
            "plant": args.get("plant"),
            "amount": None,
            "unit": None,
            "detail": "memory note",
            "notes": notes,
        }
        d = _clean_draft(raw, __plant_names(session))
        if not d:
            return None
        # The confirm step saves note drafts via /api/observations, which needs a
        # plant name — "Notebook" is the pseudo-plant for plant-less memories.
        d["plant_name"] = d["plant_name"] or "Notebook"
        return d

    if action == "reminder":
        title = (args.get("title") or "").strip()
        due = _parse_due_date(args.get("due_date") or "")
        if not title or not due:
            # Bad format or a past date — the loop asks the gardener for a fix.
            return None
        notes = (args.get("notes") or "").strip()
        return {"action": "reminder", "plant_id": None, "plant_name": None,
                "amount": None, "unit": None,
                "detail": f"due {due}",
                "notes": notes or None,
                "reminder_title": title[:200], "reminder_due": due}

    return None


def __plant_names(session: Session):
    from app.routers.ai_log import _plant_names

    return _plant_names(session)
