"""USDA hardiness-zone detection from garden coordinates.

Uses the vendored PRISM 2023 / frostline ZIP-centroid dataset
(app/data/zip_zones.bin, built by app/data/build_zip_zones.py):
nearest ZIP centroid wins. Pure stdlib, no GIS dependency.

Returns half-zones ("6b"); callers that need the app's whole-zone setting
("3".."10") use major_zone().
"""
from __future__ import annotations

import json
import struct
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
BIN_FILE = DATA_DIR / "zip_zones.bin"
META_FILE = DATA_DIR / "zip_zones_meta.json"
MAGIC = b"VZZ1"

# Plausible US bounds (incl. AK/HI/PR); outside → None, no wild guesses.
LAT_MIN, LAT_MAX = 17.0, 72.0
LON_MIN, LON_MAX = -180.0, -60.0


@lru_cache(maxsize=1)
def _table() -> tuple[list[str], list[tuple[float, float, int]]] | tuple[None, None]:
    try:
        meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        blob = BIN_FILE.read_bytes()
    except OSError:
        return None, None
    labels = meta.get("labels") or []
    if blob[:4] != MAGIC or len(labels) > 255:
        return None, None
    (count,) = struct.unpack(">I", blob[4:8])
    recs: list[tuple[float, float, int]] = []
    off = 8
    for _ in range(count):
        lat_c, lon_c, zi = struct.unpack(">hhB", blob[off : off + 5])
        off += 5
        if zi < len(labels):
            recs.append((lat_c / 100.0, lon_c / 100.0, zi))
    return labels, recs


def detect_zone(lat: float, lon: float) -> str | None:
    """Half-zone ("6b") for coordinates, or None when unknowable."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (LAT_MIN <= lat_f <= LAT_MAX and LON_MIN <= lon_f <= LON_MAX):
        return None
    labels, recs = _table()
    if not labels or not recs:
        return None
    best_zi = -1
    best_d = float("inf")
    for rlat, rlon, zi in recs:
        d = (rlat - lat_f) ** 2 + (rlon - lon_f) ** 2
        if d < best_d:
            best_d = d
            best_zi = zi
    if best_zi < 0:
        return None
    return labels[best_zi]


def major_zone(half_zone: str | None) -> str:
    """Whole-zone setting value ("6") for a half-zone ("6b")."""
    digits = "".join(ch for ch in (half_zone or "") if ch.isdigit())
    return digits or ""
