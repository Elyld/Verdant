"""CSV import — bring garden data over from other trackers.

Two-step flow, both idempotent:
  POST /api/import/preview  (multipart: entity + file) -> row mapping, counts,
      warnings, and for harvests a plant picker per row
  POST /api/import/run      (multipart: entity + file + assignments JSON)
      -> commits the rows, skipping ones already present

Supported entities: locations, plants, fertilizers, seed_sources,
watering, fertilization, harvests.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    FertilizationLog,
    Fertilizer,
    Harvest,
    Location,
    Plant,
    SeedSource,
    WateringLog,
)

router = APIRouter(prefix="/api/import", tags=["import"])

PREVIEW_SAMPLE_ROWS = 10

# Josh's Aug 2026 harvest notes: Log ID -> variety name. Used as the default
# plant suggestion in the preview; the user can change any of them.
HARVEST_PLANT_HINTS = {
    "H-2026-001": "Kellogg's Breakfast",
    "H-2026-002": "Habanero",
    "H-2026-003": "Red Scotch Bonnet",
    "H-2026-004": "Mini Yellow Bell Pepper",
    "H-2026-005": "Aji Pineapple",
    "H-2026-006": "Bosque Blue Bumblebee",
    "H-2026-007": "Sungold",
    "H-2026-008": "Fatalii",
}

ENTITIES = {
    "locations": "Locations",
    "plants": "Plants",
    "fertilizers": "Fertilizers",
    "seed_sources": "Seed sources",
    "watering": "Watering logs",
    "fertilization": "Fertilization logs",
    "harvests": "Harvest logs",
}


def _parse_date(value: Any) -> Optional[date]:
    text = (value or "").strip() if isinstance(value, str) else ""
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_int(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _read_rows(file: UploadFile) -> List[Dict[str, str]]:
    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        cleaned = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        # The export's own row-number column doesn't count as data.
        if any(v for k, v in cleaned.items() if k.lower() != "id"):
            rows.append(cleaned)
    return rows


class _Ctx:
    """Per-import lookups, shared by the row builders."""

    def __init__(self, session: Session):
        self.session = session
        self.locations = {loc.location_id: loc for loc in session.exec(select(Location)).all()}
        self.plants = {p.plant_id: p for p in session.exec(select(Plant)).all()}
        self.plants_by_variety = {p.variety_name.strip().lower(): p for p in self.plants.values()}
        self.fertilizers = {f.fertilizer_id: f for f in session.exec(select(Fertilizer)).all()}
        self.warnings: List[str] = []

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


def _resolve_location(ctx: _Ctx, code: str, log_id: str) -> Optional[Location]:
    code = (code or "").strip()
    if not code:
        return None
    loc = ctx.locations.get(code)
    if loc is None:
        ctx.warn(f"{log_id}: location '{code}' not found — import Locations first.")
    return loc


def _resolve_plants(ctx: _Ctx, code: str, log_id: str) -> List[Plant]:
    """Resolve one plant code, or several comma-separated ones."""
    codes = [c.strip() for c in (code or "").split(",") if c.strip()]
    found = []
    for c in codes:
        plant = ctx.plants.get(c)
        if plant is None:
            ctx.warn(f"{log_id}: plant '{c}' not found — import Plants first.")
        else:
            found.append(plant)
    return found


# --------------------------------------------------------------------------- #
# Row builders: (csv_row, ctx) -> dict(status, label, key, make)
# status: "new" | "skip" | "error" | "needs_plant"
# make:   callable returning the model instance to persist (for "new" rows)
# --------------------------------------------------------------------------- #

def _build_location(row: Dict[str, str], ctx: _Ctx) -> Dict[str, Any]:
    code = row.get("Location ID", "")
    name = row.get("Name", "")
    if not name:
        return {"status": "error", "label": f"{code or '?'}: missing name", "key": code}
    if code and code in ctx.locations:
        return {"status": "skip", "label": f"{code} {name}: already imported", "key": code}
    def make() -> Location:
        kwargs: dict = {}
        if code:
            kwargs["location_id"] = code
        return Location(
            name=name,
            type=row.get("Type", "") or "Container",
            light=row.get("Light", "") or "Full Sun",
            notes=row.get("Notes", "") or None,
            **kwargs,
        )
    return {"status": "new", "label": f"{code} {name}", "key": code, "make": make}


def _build_plant(row: Dict[str, str], ctx: _Ctx) -> Dict[str, Any]:
    code = row.get("Plant ID", "")
    variety = row.get("Variety Name", "")
    species = row.get("Species / Type", "")
    if not variety or not species:
        return {"status": "error", "label": f"{code or '?'}: missing variety or species", "key": code}
    if code and code in ctx.plants:
        return {"status": "skip", "label": f"{code} {variety}: already imported", "key": code}
    loc = _resolve_location(ctx, row.get("Location", ""), code or variety)
    days = _parse_int(row.get("Days to Maturity", ""))
    if row.get("Days to Maturity", "").strip() and days is None:
        ctx.warn(f"{code}: days to maturity '{row['Days to Maturity']}' is not a number — left blank.")
    def make() -> Plant:
        kwargs: dict = {}
        if code:
            kwargs["plant_id"] = code
        return Plant(
            variety_name=variety,
            species_type=species,
            family_genus=row.get("Family / Genus", "") or None,
            category=row.get("Category", "") or "Annual",
            status=row.get("Status", "") or "Growing",
            location_id=loc.id if loc else None,
            date_planted=_parse_date(row.get("Date Planted", "")),
            date_started_indoors=_parse_date(row.get("Date Started Indoors", "")),
            days_to_maturity=days,
            light=row.get("Light", "") or "Full Sun",
            notes=row.get("Notes", "") or None,
            **kwargs,
        )
    return {"status": "new", "label": f"{code} {variety}", "key": code, "make": make}


def _build_fertilizer(row: Dict[str, str], ctx: _Ctx) -> Dict[str, Any]:
    code = row.get("Fertilizer ID", "")
    name = row.get("Name", "")
    if not name:
        return {"status": "error", "label": f"{code or '?'}: missing name", "key": code}
    if code and code in ctx.fertilizers:
        return {"status": "skip", "label": f"{code} {name}: already imported", "key": code}
    def make() -> Fertilizer:
        return Fertilizer(
            fertilizer_id=code or f"FERT-{name[:12]}",
            name=name,
            npk_ratio=row.get("N-P-K", "") or None,
            best_for=row.get("Best For", "") or None,
            notes=row.get("Notes", "") or None,
        )
    return {"status": "new", "label": f"{code} {name}", "key": code, "make": make}


def _build_seed_source(row: Dict[str, str], ctx: _Ctx) -> Dict[str, Any]:
    code = row.get("Source ID", "")
    source = row.get("Source Name", "")
    if not source:
        return {"status": "error", "label": f"{code or '?'}: missing source name", "key": code}
    existing = ctx.session.exec(select(SeedSource).where(SeedSource.source_id == code)).first() if code else None
    if existing:
        return {"status": "skip", "label": f"{code} {source}: already imported", "key": code}
    plants = _resolve_plants(ctx, row.get("Link To Plant", ""), code or source)
    linked_variety = plants[0].variety_name if len(plants) == 1 else ""
    notes_parts = []
    url = row.get("Contact / URL", "")
    if url:
        notes_parts.append(f"URL: {url}")
    acquired = row.get("Year Acquired", "")
    if acquired:
        notes_parts.append(f"Acquired: {acquired}")
    harvest_year = row.get("Seed Harvest Year", "")
    if harvest_year:
        notes_parts.append(f"Seed harvest year: {harvest_year}")
    for parent_col in ("Parent A (Breeding)", "Parent B (Breeding)"):
        parent = row.get(parent_col, "")
        if parent:
            notes_parts.append(f"{parent_col.split(' (')[0]}: {parent}")
    base_notes = row.get("Notes", "")
    if base_notes:
        notes_parts.append(base_notes)
    notes = "\n".join(notes_parts) or None
    def make() -> SeedSource:
        return SeedSource(
            source_id=code or f"SRC-{source[:12]}",
            source=source,
            variety=linked_variety,  # optional since v2.5.0; backfilled from the linked plant when known
            type=row.get("Source Type", "") or "Vendor Purchase",
            linked_plant_id=plants[0].id if plants else None,
            notes=notes,
        )
    label = f"{code} {source}" + (f" ({linked_variety})" if linked_variety else "")
    return {"status": "new", "label": label, "key": code, "make": make}


def _build_watering(row: Dict[str, str], ctx: _Ctx) -> Dict[str, Any]:
    code = row.get("Log ID", "")
    if code:
        existing = ctx.session.exec(select(WateringLog).where(WateringLog.watering_id == code)).first()
        if existing:
            return {"status": "skip", "label": f"{code}: already imported", "key": code}
    loc = _resolve_location(ctx, row.get("Location", ""), code or "watering log")
    plants = _resolve_plants(ctx, row.get("Link to Plant", ""), code or "watering log")
    when = _parse_date(row.get("Date", ""))
    if when is None:
        return {"status": "error", "label": f"{code or '?'}: bad or missing date", "key": code}
    def make() -> WateringLog:
        kwargs: dict = {}
        if code:
            kwargs["watering_id"] = code
        return WateringLog(
            location_id=loc.id if loc else None,
            plant_id=plants[0].id if plants else None,
            date=when.isoformat(),
            method=row.get("Method", "") or None,
            amount=row.get("Amount", "") or None,
            notes=row.get("Notes", "") or None,
            **kwargs,
        )
    label = f"{code} {when.isoformat()} — {(loc.name if loc else row.get('Location', '')) or (plants[0].variety_name if plants else '?')}"
    return {"status": "new", "label": label, "key": code, "make": make}


def _build_fertilization(row: Dict[str, str], ctx: _Ctx) -> Dict[str, Any]:
    code = row.get("Log ID", "")
    fert_code = row.get("Fertilizer", "")
    fertilizer = ctx.fertilizers.get(fert_code) if fert_code else None
    if fert_code and fertilizer is None:
        return {"status": "error", "label": f"{code or '?'}: fertilizer '{fert_code}' not found — import Fertilizers first", "key": code}
    plants = _resolve_plants(ctx, row.get("Link to Plant", ""), code or "fertilization log")
    when = _parse_date(row.get("Date", ""))
    if when is None:
        return {"status": "error", "label": f"{code or '?'}: bad or missing date", "key": code}
    amount = row.get("Amount / Concentration", "") or None
    plant_id = plants[0].id if len(plants) == 1 else None
    notes_parts = []
    if len(plants) > 1:
        notes_parts.append("Plants: " + ", ".join(p.plant_id for p in plants))
    application = row.get("Application", "")
    if application:
        notes_parts.append(f"Application: {application}")
    base_notes = row.get("Notes", "")
    if base_notes:
        notes_parts.append(base_notes)
    notes = "\n".join(notes_parts) or None
    # Idempotency: no public log ID on this table, match on the natural key.
    stmt = select(FertilizationLog).where(
        FertilizationLog.fertilizer_id == (fertilizer.id if fertilizer else None),
        FertilizationLog.date == when.isoformat(),
        FertilizationLog.amount_used == amount,
    )
    stmt = stmt.where(FertilizationLog.plant_id == plant_id) if plant_id else stmt.where(FertilizationLog.plant_id.is_(None))
    if ctx.session.exec(stmt).first():
        return {"status": "skip", "label": f"{code} {when.isoformat()}: already imported", "key": code}
    def make() -> FertilizationLog:
        return FertilizationLog(
            date=when.isoformat(),
            fertilizer_name=fertilizer.name if fertilizer else fert_code,
            fertilizer_id=fertilizer.id if fertilizer else None,
            npk_ratio=fertilizer.npk_ratio if fertilizer else None,
            amount_used=amount,
            plant_id=plant_id,
            notes=notes,
        )
    label = f"{code} {when.isoformat()} — {fertilizer.name if fertilizer else fert_code}"
    return {"status": "new", "label": label, "key": code, "make": make}


def _build_harvest(row: Dict[str, str], ctx: _Ctx, assignments: Dict[str, Any]) -> Dict[str, Any]:
    code = row.get("Log ID", "")
    if code:
        existing = ctx.session.exec(select(Harvest).where(Harvest.harvest_id == code)).first()
        if existing:
            return {"status": "skip", "label": f"{code}: already imported", "key": code}
    when = _parse_date(row.get("Date", ""))
    quantity = _parse_int(row.get("Quantity", ""))
    problems = []
    if when is None:
        problems.append("bad or missing date")
    if quantity is None:
        problems.append("bad or missing quantity")
    plant = None
    assigned = assignments.get(code) if code else None
    if assigned:
        plant = ctx.session.get(Plant, int(assigned)) if str(assigned).isdigit() else None
    if plant is None and code in HARVEST_PLANT_HINTS:
        plant = ctx.plants_by_variety.get(HARVEST_PLANT_HINTS[code].strip().lower())
    if problems:
        return {"status": "error", "label": f"{code or '?'}: {', '.join(problems)}", "key": code}
    if plant is None:
        return {
            "status": "needs_plant",
            "label": f"{code} {when.isoformat()} — {quantity} fruit: pick a plant",
            "key": code,
            "hint_variety": HARVEST_PLANT_HINTS.get(code),
        }
    # Natural-key dedup in case the log ID wasn't preserved.
    dup = ctx.session.exec(
        select(Harvest).where(
            Harvest.plant_id == plant.id,
            Harvest.date == when.isoformat(),
            Harvest.quantity == quantity,
        )
    ).first()
    if dup:
        return {"status": "skip", "label": f"{code} {when.isoformat()}: already imported", "key": code}
    def make() -> Harvest:
        kwargs: dict = {}
        if code:
            kwargs["harvest_id"] = code
        return Harvest(
            plant_id=plant.id,
            date=when.isoformat(),
            quantity=quantity,
            unit=row.get("Unit", "") or "fruit",
            notes=row.get("Notes", "") or None,
            **kwargs,
        )
    return {"status": "new", "label": f"{code} {when.isoformat()} — {quantity} × {plant.variety_name}", "key": code, "make": make}


BUILDERS = {
    "locations": _build_location,
    "plants": _build_plant,
    "fertilizers": _build_fertilizer,
    "seed_sources": _build_seed_source,
    "watering": _build_watering,
    "fertilization": _build_fertilization,
}


def _process(entity: str, rows: List[Dict[str, str]], ctx: _Ctx, assignments: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for row in rows:
        if entity == "harvests":
            results.append(_build_harvest(row, ctx, assignments))
        else:
            results.append(BUILDERS[entity](row, ctx))
    return results


def _plant_options(session: Session) -> List[Dict[str, Any]]:
    plants = session.exec(select(Plant).order_by(Plant.variety_name)).all()
    return [{"id": p.id, "plant_id": p.plant_id, "variety_name": p.variety_name} for p in plants]


@router.post("/preview")
async def preview_import(
    entity: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    if entity not in ENTITIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown entity '{entity}'.")
    rows = _read_rows(file)
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No data rows found in the CSV.")
    ctx = _Ctx(session)
    results = _process(entity, rows, ctx, assignments={})
    counts = {"new": 0, "skip": 0, "error": 0, "needs_plant": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    sample = [
        {"key": r.get("key"), "status": r["status"], "label": r["label"], "hint_variety": r.get("hint_variety")}
        for r in results[:PREVIEW_SAMPLE_ROWS]
    ]
    payload: Dict[str, Any] = {
        "entity": entity,
        "entity_label": ENTITIES[entity],
        "total_rows": len(rows),
        "counts": counts,
        "warnings": ctx.warnings[:20],
        "sample": sample,
        "truncated": len(results) > PREVIEW_SAMPLE_ROWS,
    }
    if entity == "harvests":
        options = _plant_options(session)
        by_variety = {o["variety_name"].strip().lower(): o["id"] for o in options}
        suggested = {}
        assign_rows = []
        for r in results:
            if r["status"] == "needs_plant":
                assign_rows.append({"key": r["key"], "label": r["label"], "hint_variety": r.get("hint_variety")})
                if r.get("hint_variety"):
                    match = by_variety.get(r["hint_variety"].strip().lower())
                    if match:
                        suggested[r["key"]] = match
        payload["plant_options"] = options
        payload["assign_rows"] = assign_rows
        payload["suggested_assignments"] = suggested
        payload["needs_plants_first"] = not options
    return payload


@router.post("/run")
async def run_import(
    entity: str = Form(...),
    file: UploadFile = File(...),
    assignments: str = Form("{}"),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    if entity not in ENTITIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown entity '{entity}'.")
    try:
        assignment_map = json.loads(assignments or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="assignments is not valid JSON.")
    rows = _read_rows(file)
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No data rows found in the CSV.")
    ctx = _Ctx(session)
    results = _process(entity, rows, ctx, assignments=assignment_map if isinstance(assignment_map, dict) else {})
    imported, skipped, errors = 0, 0, []
    for r in results:
        if r["status"] == "new":
            try:
                session.add(r["make"]())
                imported += 1
            except Exception as exc:  # noqa: BLE001 - report per-row, keep going
                errors.append(f"{r.get('key') or '?'}: {exc}")
        elif r["status"] == "skip":
            skipped += 1
        else:
            errors.append(f"{r.get('key') or '?'}: {r['label']}")
    session.commit()
    # Refresh lookups so a second file in the same session sees new rows.
    return {
        "entity": entity,
        "entity_label": ENTITIES[entity],
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:20],
        "warnings": ctx.warnings[:20],
    }
