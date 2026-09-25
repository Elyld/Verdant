"""Current weather via Open-Meteo (free, no API key required).

Used to stamp observations with the weather at log time. Configure with:
  GARDEN_LAT=...  GARDEN_LON=...
If unset, weather capture is skipped silently.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional


def _coords() -> Optional[tuple[float, float]]:
    try:
        lat = float(os.getenv("GARDEN_LAT", ""))
        lon = float(os.getenv("GARDEN_LON", ""))
    except (TypeError, ValueError):
        return None
    return (lat, lon)


def _summarize(code: int) -> str:
    if code == 0:
        return "Clear"
    if code in (1, 2, 3):
        return "Partly cloudy"
    if code in (45, 48):
        return "Foggy"
    if code in (51, 53, 55, 56, 57):
        return "Drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Overcast"


def fetch_current_weather() -> Optional[dict]:
    """Return {'temp_c': float, 'summary': str} or None if unavailable.

    Never raises: any failure (no coords, no network, bad payload) → None.
    """
    coords = _coords()
    if coords is None:
        return None
    lat, lon = coords
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,weather_code"
        "&timezone=auto"
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "verdant-garden-log"})
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        current = payload.get("current") or {}
        temp = current.get("temperature_2m")
        code = current.get("weather_code")
        if temp is None or code is None:
            return None
        return {"temp_c": round(float(temp), 1), "summary": _summarize(int(code))}
    except Exception:
        return None


def configured() -> bool:
    return _coords() is not None
