"""Pest & disease guide — a bundled, offline reference for the Pests page.

40 common vegetable-garden pests and diseases, each with identification
signs, organic + conventional treatments, and prevention, compiled from
university extension guidance. Instant, private, no API key, no network.

Endpoints:
  GET /api/pest-guide/            all entries (summaries)
  GET /api/pest-guide/search?q=   full entries matching name/hosts/signs
  GET /api/pest-guide/for-host?host=tomato
  GET /api/pest-guide/{slug}      one full entry
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/pest-guide", tags=["pest-guide"])

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "pests.json"

GUIDE_SOURCE = "Pest & disease guide"


@lru_cache(maxsize=1)
def _pests() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)["pests"]


def _summary(p: dict) -> dict:
    return {
        "slug": p["slug"],
        "name": p["name"],
        "type": p["type"],
        "hosts": p["hosts"],
        "source": GUIDE_SOURCE,
    }


def _full(p: dict) -> dict:
    return {**_summary(p), **{
        "signs": p["signs"],
        "treatment_organic": p["treatment_organic"],
        "treatment_conventional": p["treatment_conventional"],
        "prevention": p["prevention"],
        "sources": p["sources"],
    }}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    # tolerate tomato/tomatoes, squash/squashes
    if s.endswith("es") and len(s) > 4:
        s = s[:-2]
    elif s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s


@router.get("/")
def list_guide() -> list[dict]:
    return [_summary(p) for p in _pests()]


@router.get("/search")
def search_guide(q: str = Query("", description="match against name, hosts, signs")) -> list[dict]:
    q = _norm(q)
    if not q:
        return []
    out = []
    for p in _pests():
        hay = " ".join([p["name"], p["type"], " ".join(p["hosts"]), p["signs"]]).lower()
        # name match wins first, then host, then anything
        if q in p["name"].lower():
            out.insert(0, _full(p))
        elif any(q in _norm(h) or _norm(h) in q for h in p["hosts"]):
            out.append(_full(p))
        elif q in hay:
            out.append(_full(p))
    # de-dupe (a pest can match name and host)
    seen = set()
    deduped = []
    for p in out:
        if p["slug"] not in seen:
            seen.add(p["slug"])
            deduped.append(p)
    return deduped


@router.get("/for-host")
def for_host(host: str = Query(..., description="e.g. tomato")) -> list[dict]:
    host = _norm(host)
    return [
        _full(p) for p in _pests()
        if any(_norm(h) == host or _norm(h) in host or host in _norm(h) for h in p["hosts"])
    ]


@router.get("/{slug}")
def get_entry(slug: str) -> dict:
    for p in _pests():
        if p["slug"] == slug:
            return _full(p)
    raise HTTPException(status_code=404, detail=f"No guide entry for '{slug}'")
