"""Plant identification via the PlantNet API (https://my.plantnet.org).

Free tier, keyed per user — the key lives in Settings and a photo is only
ever uploaded when the user taps "Identify". Never raises: failures come
back as {"ok": False, "reason": ...}.
"""
from __future__ import annotations

import httpx

IDENTIFY_URL = "https://my.plantnet.org/v2/identify/all"
TIMEOUT_S = 30.0
MAX_RESULTS = 5


def identify(
    image_bytes: bytes, filename: str, api_key: str, organ: str = "auto"
) -> dict:
    """Identify a plant from a photo. Returns {"ok": True, "results": [...]}
    with the top candidates, or {"ok": False, "reason": ...}."""
    if not api_key:
        return {"ok": False, "reason": "no-key"}
    if not image_bytes:
        return {"ok": False, "reason": "empty-image"}
    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            resp = client.post(
                IDENTIFY_URL,
                params={"api-key": api_key, "nb-results": MAX_RESULTS},
                files={"images": (filename or "photo.jpg", image_bytes)},
                data={"organs": [organ]},
            )
    except Exception:
        return {"ok": False, "reason": "unreachable"}
    if resp.status_code == 401:
        return {"ok": False, "reason": "bad-key"}
    if resp.status_code == 429:
        return {"ok": False, "reason": "rate-limited"}
    if resp.status_code != 200:
        return {"ok": False, "reason": f"http-{resp.status_code}"}
    try:
        payload = resp.json()
    except ValueError:
        return {"ok": False, "reason": "bad-response"}
    results = []
    for r in (payload.get("results") or [])[:MAX_RESULTS]:
        species = r.get("species") or {}
        family = species.get("family") or {}
        results.append(
            {
                "name": species.get("scientificNameWithoutAuthor") or "",
                "common_names": list(species.get("commonNames") or [])[:3],
                "family": family.get("scientificNameWithoutAuthor") or "",
                "score": round(float(r.get("score") or 0) * 100, 1),
            }
        )
    results = [r for r in results if r["name"]]
    if not results:
        return {"ok": False, "reason": "no-match"}
    return {"ok": True, "results": results}
