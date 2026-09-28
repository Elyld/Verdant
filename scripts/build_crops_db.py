"""Build app/data/crops.json: the 30 curated crops + the OpenPlantDB edible subset.

OpenPlantDB (https://github.com/cwfrazier1/openplantdb) is a CC0 public-domain
flat JSON of ~25k plants with real growing data: germination/maturity ranges,
spacing, sun, sowing method, and 2-4 sentence growing directions per entry.
No API, no key — just a file in git, so the crop guide stays offline.

This script merges:
  1. The existing curated crops.json entries (kept verbatim — they carry our
     hand-written varieties, family info, and Growstuff community mappings).
  2. Every OpenPlantDB entry in the edible categories (vegetable, herb,
     berry, fruit), mapped onto the same schema, EXCEPT slugs that collide
     with a curated key (the curated entry wins those).

Usage:
    python3 scripts/build_crops_db.py [path/to/openplantdb-plants.json]

With no argument, downloads plants.json from the OpenPlantDB repo (~56MB).

Output: app/data/crops.json — curated entries first (original order), then
OpenPlantDB entries sorted by name. Deterministic: same input → same file.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_FILE = REPO / "app" / "data" / "crops.json"
OPENPLANTDB_URL = (
    "https://raw.githubusercontent.com/cwfrazier1/openplantdb/main/plants.json"
)
EDIBLE = {"vegetable", "herb", "berry", "fruit"}
SUN_MAP = {"full": "Full Sun", "partial": "Partial Shade", "shade": "Full Shade"}


def _rng(d: dict | None, unit: str = "") -> str:
    if not isinstance(d, dict):
        return ""
    lo, hi = d.get("min"), d.get("max")
    if lo is None:
        return ""
    s = f"{lo}–{hi}{unit}" if hi is not None and hi != lo else f"{lo}{unit}"
    return s


def _mid(d: dict | None) -> int | None:
    if not isinstance(d, dict):
        return None
    lo, hi = d.get("min"), d.get("max")
    if lo is None:
        return None
    return round((lo + (hi if hi is not None else lo)) / 2)


def map_entry(p: dict) -> dict | None:
    slug = (p.get("slug") or "").strip()
    name = (p.get("common_name") or "").strip()
    maturity = _mid(p.get("days_to_maturity"))
    if not slug or not name or maturity is None:
        return None
    sci = (p.get("scientific_name") or "").strip()
    aliases = [sci] if sci and sci.lower() != name.lower() else []

    mat = p.get("days_to_maturity") or {}
    mfrom = (p.get("maturity_from") or "").strip()
    desc = (p.get("directions") or "").strip()
    timing = f"Matures in {_rng(mat)} days" + (f" from {mfrom}" if mfrom else "") + "."
    description = f"{desc} {timing}".strip() if desc else timing

    return {
        "key": slug,
        "name": name,
        "aliases": aliases,
        "days_to_maturity": maturity,
        "days_to_germination": _rng(p.get("days_to_germination")),
        "description": description,
        "family": "",
        "sun": SUN_MAP.get((p.get("sun") or "").strip().lower(), ""),
        "spacing_in": _rng(p.get("spacing_in")),
        "sowing_depth_in": "",
        "varieties": [],
        "source": "OpenPlantDB",
    }


def load_openplantdb(path: str | None) -> list[dict]:
    if path:
        raw = Path(path).read_text(encoding="utf-8")
    else:
        print(f"downloading {OPENPLANTDB_URL} ...", flush=True)
        with urllib.request.urlopen(OPENPLANTDB_URL, timeout=120) as r:
            raw = r.read().decode("utf-8")
    data = json.loads(raw)
    items = list(data.values()) if isinstance(data, dict) else data
    return [p for p in items if isinstance(p, dict) and p.get("category") in EDIBLE]


def main() -> None:
    curated = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    curated_keys = {c["key"] for c in curated}

    new_entries: dict[str, dict] = {}
    skipped_collision = 0
    for p in load_openplantdb(sys.argv[1] if len(sys.argv) > 1 else None):
        slug = (p.get("slug") or "").strip()
        if not slug or slug in curated_keys or slug in new_entries:
            skipped_collision += 1
            continue
        entry = map_entry(p)
        if entry:
            new_entries[slug] = entry
        else:
            skipped_collision += 1

    merged = curated + sorted(new_entries.values(), key=lambda e: e["name"].lower())
    DATA_FILE.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"curated: {len(curated)}, openplantdb: {len(new_entries)}, "
          f"skipped: {skipped_collision}, total: {len(merged)}")
    print(f"wrote {DATA_FILE} ({DATA_FILE.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
