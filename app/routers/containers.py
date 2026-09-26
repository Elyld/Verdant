"""API router for garden containers (backyard builder)."""
import re
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from app import frost as frost_mod
from app import units as units_mod
from app.database import get_session
from app.models import Container, Harvest, Plant, Planting

router = APIRouter(prefix="/api/containers", tags=["containers"])

GRID_COLS_DEFAULT, GRID_ROWS_DEFAULT = 24, 16
GRID_MIN, GRID_MAX = 4, 60


class PlantingRead(SQLModel):
    id: int
    container_id: int
    plant_id: int
    season_year: int
    slot: int = 0
    notes: str = ""
    variety_name: str = ""
    species_type: str = ""
    family_genus: Optional[str] = None


class RotationWarning(SQLModel):
    container_id: int
    container_name: str
    variety_name: str
    prev_variety_name: str
    prev_year: int
    reason: str


def _get_or_404(session: Session, container_id: int) -> Container:
    container = session.get(Container, container_id)
    if not container:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found")
    return container


def grid_dims(session: Session) -> tuple:
    """Planner grid size in cells (1 cell = 1 ft), from settings."""
    try:
        cols = int(frost_mod.get_setting(session, "planner_grid_cols") or GRID_COLS_DEFAULT)
    except (TypeError, ValueError):
        cols = GRID_COLS_DEFAULT
    try:
        rows = int(frost_mod.get_setting(session, "planner_grid_rows") or GRID_ROWS_DEFAULT)
    except (TypeError, ValueError):
        rows = GRID_ROWS_DEFAULT
    cols = max(GRID_MIN, min(GRID_MAX, cols))
    rows = max(GRID_MIN, min(GRID_MAX, rows))
    return cols, rows


def default_footprint(kind: str, size: str) -> tuple:
    """Default grid footprint (w, h cells) for a container kind."""
    if (kind or "") == "raised bed":
        m = re.search(r"(\d+)\s*[x×]\s*(\d+)", size or "")
        if m:
            return max(1, int(m.group(1))), max(1, int(m.group(2)))
        return (4, 4)
    return {
        "grow bag": (2, 2), "pot": (1, 1), "planter": (3, 1),
        "arch": (4, 4), "pallet": (4, 3),
    }.get(kind or "", (2, 2))


def default_height(kind: str) -> Optional[float]:
    """Default height in feet for a container kind (used by the 3D view)."""
    return {"arch": 7.0}.get(kind or "")


def _rects_overlap(ax, ay, aw, ah, bx, by, bw, bh) -> bool:
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def first_free_spot(session: Session, year: int, w: int, h: int, cols: int, rows: int,
                    ignore_id: Optional[int] = None) -> tuple:
    """Scan for the first grid position that doesn't overlap existing containers."""
    others = session.query(Container).filter(Container.season_year == year).all()
    rects = [(c.grid_x or 0, c.grid_y or 0, c.grid_w or 1, c.grid_h or 1)
             for c in others if c.id != ignore_id and c.grid_x is not None]
    for gy in range(0, rows - h + 1):
        for gx in range(0, cols - w + 1):
            if not any(_rects_overlap(gx, gy, w, h, *r) for r in rects):
                return gx, gy
    return 0, 0


def backfill_grids(session: Session, containers: List[Container]) -> None:
    """One-time migration: legacy x/y percent positions -> grid cells."""
    cols, rows = grid_dims(session)
    changed = False
    for c in containers:
        if c.grid_x is not None and c.grid_y is not None and c.grid_w and c.grid_h:
            continue
        w, h = default_footprint(c.kind, c.size)
        w, h = min(w, cols), min(h, rows)
        gx = max(0, min(cols - w, round((c.x or 10) / 100 * cols)))
        gy = max(0, min(rows - h, round((c.y or 10) / 100 * rows)))
        c.grid_x, c.grid_y, c.grid_w, c.grid_h = gx, gy, w, h
        session.add(c)
        changed = True
    if changed:
        session.commit()


def backfill_plantings(session: Session, containers: List[Container]) -> None:
    """One-time migration: legacy single plant_id -> plantings rows."""
    changed = False
    for c in containers:
        if not c.plant_id:
            continue
        exists = session.query(Planting).filter(
            Planting.container_id == c.id, Planting.season_year == c.season_year
        ).first()
        if exists:
            continue
        session.add(Planting(container_id=c.id, plant_id=c.plant_id,
                             season_year=c.season_year, slot=0))
        changed = True
    if changed:
        session.commit()


def ensure_backfilled(session: Session, year: Optional[int] = None) -> None:
    """Run the grid + plantings one-time migrations for a season's containers."""
    query = session.query(Container)
    if year is not None:
        query = query.filter(Container.season_year == year)
    containers = query.all()
    backfill_grids(session, containers)
    backfill_plantings(session, containers)


def _planting_read(p: Planting) -> PlantingRead:
    plant = p.plant
    return PlantingRead(
        id=p.id, container_id=p.container_id, plant_id=p.plant_id,
        season_year=p.season_year, slot=p.slot or 0, notes=p.notes or "",
        variety_name=(plant.variety_name if plant else ""),
        species_type=(plant.species_type if plant else ""),
        family_genus=(plant.family_genus if plant else None),
    )


@router.get("/", response_model=List[Container])
def list_containers(
    year: Optional[int] = Query(None, description="Season year"),
    session: Session = Depends(get_session),
) -> List[Container]:
    query = session.query(Container).order_by(Container.name)
    if year is not None:
        query = query.filter(Container.season_year == year)
    containers = query.all()
    backfill_grids(session, containers)
    backfill_plantings(session, containers)
    return containers


@router.get("/years", response_model=List[int])
def list_years(session: Session = Depends(get_session)) -> List[int]:
    rows = session.query(Container.season_year).distinct().order_by(Container.season_year.desc()).all()
    return [r[0] for r in rows]


@router.get("/grid")
def get_grid(session: Session = Depends(get_session)) -> dict:
    cols, rows = grid_dims(session)
    return {"cols": cols, "rows": rows}


@router.put("/grid")
def save_grid(payload: dict, session: Session = Depends(get_session)) -> dict:
    try:
        cols = int(payload.get("cols", GRID_COLS_DEFAULT))
        rows = int(payload.get("rows", GRID_ROWS_DEFAULT))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="cols and rows must be numbers")
    if not (GRID_MIN <= cols <= GRID_MAX and GRID_MIN <= rows <= GRID_MAX):
        raise HTTPException(status_code=422,
                            detail=f"cols and rows must be between {GRID_MIN} and {GRID_MAX}")
    frost_mod.set_setting(session, "planner_grid_cols", str(cols))
    frost_mod.set_setting(session, "planner_grid_rows", str(rows))
    session.commit()
    return {"cols": cols, "rows": rows}


@router.get("/plantings", response_model=List[PlantingRead])
def list_plantings(
    year: Optional[int] = Query(None, description="Season year"),
    session: Session = Depends(get_session),
) -> List[PlantingRead]:
    ensure_backfilled(session, year)
    query = session.query(Planting).order_by(Planting.slot, Planting.id)
    if year is not None:
        query = query.filter(Planting.season_year == year)
    return [_planting_read(p) for p in query.all()]


@router.post("/plantings", response_model=PlantingRead, status_code=201)
def add_planting(payload: dict, session: Session = Depends(get_session)) -> PlantingRead:
    try:
        container_id = int(payload["container_id"])
        plant_id = int(payload["plant_id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="container_id and plant_id are required")
    container = _get_or_404(session, container_id)
    plant = session.get(Plant, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail=f"Plant {plant_id} not found")
    existing = session.query(Planting).filter(
        Planting.container_id == container_id,
        Planting.plant_id == plant_id,
        Planting.season_year == container.season_year,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="That plant is already in this container")
    planting = Planting(
        container_id=container_id, plant_id=plant_id,
        season_year=container.season_year,
        slot=int(payload.get("slot", 0) or 0),
        notes=(payload.get("notes") or "").strip(),
    )
    session.add(planting)
    session.commit()
    session.refresh(planting)
    return _planting_read(planting)


@router.delete("/plantings/{planting_id}", status_code=204)
def remove_planting(planting_id: int, session: Session = Depends(get_session)) -> None:
    planting = session.get(Planting, planting_id)
    if not planting:
        raise HTTPException(status_code=404, detail=f"Planting {planting_id} not found")
    session.delete(planting)
    session.commit()


def _same_family(a: Plant, b: Plant) -> bool:
    if not a or not b:
        return False
    fa = (a.family_genus or "").strip().lower()
    fb = (b.family_genus or "").strip().lower()
    if fa and fb:
        return fa == fb
    sa = (a.species_type or "").strip().lower()
    sb = (b.species_type or "").strip().lower()
    return bool(sa and sa == sb)


@router.get("/rotation-warnings", response_model=List[RotationWarning])
def rotation_warnings(
    year: int = Query(..., description="Season year to check"),
    session: Session = Depends(get_session),
) -> List[RotationWarning]:
    """Flag plantings whose plant family grew in the same container last season."""
    ensure_backfilled(session)
    prev = session.query(Planting).filter(Planting.season_year == year - 1).all()
    by_name: dict = {}
    for p in prev:
        if p.container:
            by_name.setdefault(p.container.name, []).append(p.plant)
    current = session.query(Planting).filter(Planting.season_year == year).all()
    warnings: List[RotationWarning] = []
    seen = set()
    for p in current:
        container = p.container
        if not container:
            continue
        for q in by_name.get(container.name, []):
            if _same_family(p.plant, q):
                key = (container.id, (q.species_type or q.variety_name or "").lower())
                if key in seen:
                    continue
                seen.add(key)
                label = q.species_type or q.variety_name or "the same crop"
                warnings.append(RotationWarning(
                    container_id=container.id,
                    container_name=container.name,
                    variety_name=p.plant.variety_name if p.plant else "",
                    prev_variety_name=q.variety_name if q else "",
                    prev_year=year - 1,
                    reason=f"{label} grew here in {year - 1} — consider rotating",
                ))
    return warnings


@router.get("/yield-map")
def yield_map(
    year: int = Query(..., description="Season year to total harvest weight for"),
    session: Session = Depends(get_session),
) -> dict:
    """Total harvested weight (oz) per container for a season, via plantings.

    Keyed by container *name* — names are the stable identity across seasons
    (container rows are per-season), matching the rotation-warning convention.
    Rows without a recorded weight are skipped.
    """
    ensure_backfilled(session)
    totals: dict = {}
    harvests = session.query(Harvest).filter(Harvest.date.like(f"{year}%")).all()
    for h in harvests:
        oz = units_mod.to_oz(h.weight, h.weight_unit)
        if oz is None or oz <= 0:
            continue
        planting = (
            session.query(Planting)
            .filter(Planting.plant_id == h.plant_id, Planting.season_year == year)
            .first()
        )
        if not planting or not planting.container or not planting.container.name:
            continue
        key = planting.container.name
        totals[key] = round(totals.get(key, 0.0) + oz, 1)
    return {"year": year, "unit": "oz", "totals": totals}


@router.post("/", response_model=Container, status_code=201)
def create_container(payload: dict, session: Session = Depends(get_session)) -> Container:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    kind = (payload.get("kind") or "grow bag").strip()
    size = (payload.get("size") or "").strip()
    year = int(payload.get("season_year") or date.today().year)
    cols, rows = grid_dims(session)
    dw, dh = default_footprint(kind, size)
    try:
        w = max(1, min(cols, int(payload.get("grid_w", dw))))
        h = max(1, min(rows, int(payload.get("grid_h", dh))))
    except (TypeError, ValueError):
        w, h = dw, dh
    gx, gy = first_free_spot(session, year, w, h, cols, rows)
    raw_h = payload.get("height_ft")
    try:
        height_ft = float(raw_h) if raw_h not in (None, "") else default_height(kind)
    except (TypeError, ValueError):
        height_ft = default_height(kind)
    if height_ft is not None:
        height_ft = max(0.5, height_ft)
    container = Container(
        name=name,
        kind=kind,
        size=size,
        volume_value=payload.get("volume_value"),
        volume_unit=(payload.get("volume_unit") or "").strip().lower(),
        height_ft=height_ft,
        location_id=payload.get("location_id"),
        season_year=year,
        x=float(payload.get("x", 10)),
        y=float(payload.get("y", 10)),
        grid_x=gx, grid_y=gy, grid_w=w, grid_h=h,
        plant_id=payload.get("plant_id"),
        soil_notes=(payload.get("soil_notes") or "").strip(),
    )
    session.add(container)
    session.commit()
    session.refresh(container)
    return container


@router.get("/{container_id}", response_model=Container)
def get_container(container_id: int, session: Session = Depends(get_session)) -> Container:
    return _get_or_404(session, container_id)


@router.patch("/{container_id}", response_model=Container)
def update_container(
    container_id: int, payload: dict, session: Session = Depends(get_session)
) -> Container:
    container = _get_or_404(session, container_id)
    for key, value in payload.items():
        if hasattr(container, key) and key != "id":
            if key in ("grid_x", "grid_y") and value is not None:
                value = max(0, int(value))
            if key in ("grid_w", "grid_h") and value is not None:
                value = max(1, int(value))
            if key == "height_ft":
                value = None if value in (None, "") else max(0.5, float(value))
            setattr(container, key, value)
    session.add(container)
    session.commit()
    session.refresh(container)
    return container


@router.delete("/{container_id}", status_code=204)
def delete_container(container_id: int, session: Session = Depends(get_session)) -> None:
    container = _get_or_404(session, container_id)
    session.query(Planting).filter(Planting.container_id == container.id).delete()
    session.delete(container)
    session.commit()


@router.post("/copy-season", response_model=List[Container])
def copy_season(
    payload: dict, session: Session = Depends(get_session)
) -> List[Container]:
    """Copy one season's layout into another year (grid, plantings included)."""
    try:
        from_year = int(payload["from_year"])
        to_year = int(payload["to_year"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="from_year and to_year are required")
    if from_year == to_year:
        raise HTTPException(status_code=422, detail="from_year and to_year must differ")
    existing = session.query(Container).filter(Container.season_year == to_year).count()
    if existing:
        raise HTTPException(status_code=409, detail=f"Season {to_year} already has containers")
    sources = session.query(Container).filter(Container.season_year == from_year).all()
    copies = []
    id_map = {}
    for src in sources:
        copy = Container(
            name=src.name, kind=src.kind, size=src.size,
            volume_value=src.volume_value, volume_unit=src.volume_unit,
            height_ft=src.height_ft,
            location_id=src.location_id, season_year=to_year,
            x=src.x, y=src.y,
            grid_x=src.grid_x, grid_y=src.grid_y,
            grid_w=src.grid_w, grid_h=src.grid_h,
            plant_id=src.plant_id, soil_notes=src.soil_notes,
        )
        session.add(copy)
        session.flush()
        id_map[src.id] = copy.id
        copies.append(copy)
    old_plantings = session.query(Planting).filter(
        Planting.container_id.in_(list(id_map.keys()))
    ).all() if id_map else []
    for p in old_plantings:
        session.add(Planting(
            container_id=id_map[p.container_id], plant_id=p.plant_id,
            season_year=to_year, slot=p.slot, notes=p.notes,
        ))
    session.commit()
    for copy in copies:
        session.refresh(copy)
    return copies
