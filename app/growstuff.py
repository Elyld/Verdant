"""Growstuff community-data enrichment for the bundled crop guide.

https://www.growstuff.org/crops/<slug>.json is free, keyless, and reports
crowd-sourced medians (median_days_to_first_harvest, median_lifespan,
plantings_count, ...) per crop. The bundled crops.json stays the offline
source of truth; Growstuff medians enrich it when reachable.

Caching: fetched payloads are trimmed and stored on disk
(GARDEN_DATA_DIR/growstuff_cache.json) with a 7-day TTL. Refreshes happen
in a daemon thread triggered by crop searches, so API requests never wait
on the network and the guide works fully offline. Never raises.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from datetime import datetime, timezone

from app.database import DATA_DIR

CACHE_FILE = DATA_DIR / "growstuff_cache.json"
TTL_S = 7 * 24 * 3600
FETCH_TIMEOUT_S = 12

# Verdant crop key -> Growstuff slug. Keys not listed here default to the
# key itself; slugs that 404 are skipped silently at fetch time.
CROP_SLUGS = {
    "tomato": "tomato",
    "pepper-bell": "bell-pepper",
    "pepper-hot": "chilli-pepper",
    "cucumber": "cucumber",
    "zucchini": "zucchini",
    "winter-squash": "butternut-squash",
    "basil": "basil",
    "lettuce": "lettuce",
    "spinach": "spinach",
    "kale": "kale",
    "carrot": "carrot",
    "radish": "radish",
    "beet": "beet",
    "bush-bean": "bush-bean",
    "pole-bean": "runner-bean",
    "pea": "pea",
    "onion": "onion",
    "garlic": "garlic",
    "potato": "potato",
    "sweet-potato": "sweet-potato",
    "corn": "corn",
    "eggplant": "eggplant",
    "okra": "okra",
    "cilantro": "coriander",
    "dill": "dill",
    "parsley": "parsley",
    "chives": "chives",
    "thyme": "thyme",
    "oregano": "oregano",
    "rosemary": "rosemary",
}

TRIM_FIELDS = (
    "median_days_to_first_harvest",
    "median_lifespan",
    "plantings_count",
    "harvests_count",
    "sowing_method",
    "sun_requirements",
)

_mem = {"at": 0.0, "data": {}}
_refresh_running = False
_refresh_lock = threading.Lock()


def _read_disk() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _fresh(entry: dict) -> bool:
    try:
        fetched = datetime.fromisoformat(entry.get("fetched_at", ""))
    except (ValueError, TypeError):
        return False
    now = datetime.now(timezone.utc)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (now - fetched).total_seconds() < TTL_S


def _cached() -> dict:
    now = time.monotonic()
    if now - _mem["at"] < 300:
        return _mem["data"]
    data = _read_disk()
    _mem["at"] = now
    _mem["data"] = data
    return data


def get(crop_key: str) -> dict | None:
    """Trimmed community data for a Verdant crop key, or None.

    Only returns entries with a usable harvest median; never raises.
    """
    entry = _cached().get(crop_key or "")
    if not entry or not _fresh(entry):
        return None
    if not entry.get("median_days_to_first_harvest"):
        return None
    return entry


def _fetch_slug(slug: str) -> dict | None:
    url = f"https://www.growstuff.org/crops/{slug}.json"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "verdant-garden-log"}
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    trimmed = {
        f: payload.get(f) for f in TRIM_FIELDS if payload.get(f) not in (None, "")
    }
    if not trimmed.get("median_days_to_first_harvest"):
        return None
    trimmed["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return trimmed


def _refresh_all() -> None:
    global _refresh_running
    try:
        data = _read_disk()
        for key, slug in CROP_SLUGS.items():
            entry = data.get(key)
            if entry and _fresh(entry):
                continue
            fetched = _fetch_slug(slug)
            if fetched:
                data[key] = fetched
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(CACHE_FILE)
        _mem["at"] = 0.0  # force re-read
    except Exception:
        pass
    finally:
        with _refresh_lock:
            _refresh_running = False


def refresh_if_stale() -> None:
    """Kick off a background refresh when any crop's cache is stale.

    Returns immediately; the refresh runs in a daemon thread. Safe to call
    from request handlers. Never raises.
    """
    global _refresh_running
    try:
        data = _cached()
        stale = any(
            not (data.get(k) and _fresh(data[k])) for k in CROP_SLUGS
        )
        if not stale:
            return
        with _refresh_lock:
            if _refresh_running:
                return
            _refresh_running = True
        thread = threading.Thread(target=_refresh_all, daemon=True)
        thread.start()
    except Exception:
        pass
