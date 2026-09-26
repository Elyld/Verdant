"""Current weather via Open-Meteo (free, no API key required).

Used to stamp observations with the weather at log time. Configure with:
  GARDEN_LAT=...  GARDEN_LON=...
If unset, weather capture is skipped silently.
"""

from __future__ import annotations

import json
import os
import time
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


# --------------------------------------------------------------------------- #
# Forecast (hourly + daily), cached server-side so the UI stays fast.
# --------------------------------------------------------------------------- #
FORECAST_TTL_S = 1800  # 30 minutes
_forecast_cache = {"at": 0.0, "data": None}


def fetch_forecast() -> Optional[dict]:
    """Fetch and compact the Open-Meteo forecast. Never raises.

    Returns imperial units (F, mph, inches) — the router converts to C when
    the user's temperature_unit setting says so. Shape:
      {"as_of": iso, "current": {...}, "hourly": [...48], "daily": [...7]}
    """
    coords = _coords()
    if coords is None:
        return None
    lat, lon = coords
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_gusts_10m"
        "&hourly=temperature_2m,precipitation_probability,precipitation,"
        "relative_humidity_2m,wind_gusts_10m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
        "precipitation_sum,wind_gusts_10m_max"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
        "&timezone=auto&forecast_days=7"
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "verdant-garden-log"})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    try:
        current = payload.get("current") or {}
        hourly = payload.get("hourly") or {}
        daily = payload.get("daily") or {}
        htime = hourly.get("time") or []
        n = min(48, len(htime))

        def hcol(name):
            col = hourly.get(name) or []
            return [col[i] if i < len(col) else None for i in range(n)]

        htemp, hprob, hprecip, hrh, hgust = (
            hcol("temperature_2m"), hcol("precipitation_probability"),
            hcol("precipitation"), hcol("relative_humidity_2m"),
            hcol("wind_gusts_10m"),
        )
        hours = [
            {
                "t": htime[i],
                "temp_f": htemp[i],
                "precip_prob": hprob[i],
                "precip_in": hprecip[i],
                "rh": hrh[i],
                "gust_mph": hgust[i],
            }
            for i in range(n)
        ]
        dtime = daily.get("time") or []
        m = len(dtime)

        def dcol(name):
            col = daily.get(name) or []
            return [col[i] if i < len(col) else None for i in range(m)]

        dmax, dmin, dprob, dprecip, dgust = (
            dcol("temperature_2m_max"), dcol("temperature_2m_min"),
            dcol("precipitation_probability_max"), dcol("precipitation_sum"),
            dcol("wind_gusts_10m_max"),
        )
        days = [
            {
                "date": dtime[i],
                "tmax_f": dmax[i],
                "tmin_f": dmin[i],
                "precip_prob": dprob[i],
                "precip_in": dprecip[i],
                "gust_mph": dgust[i],
            }
            for i in range(m)
        ]
        return {
            "as_of": current.get("time"),
            "current": {
                "temp_f": current.get("temperature_2m"),
                "summary": _summarize(int(current.get("weather_code") or 0)),
                "rh": current.get("relative_humidity_2m"),
                "wind_mph": current.get("wind_speed_10m"),
                "gust_mph": current.get("wind_gusts_10m"),
            },
            "hourly": hours,
            "daily": days,
        }
    except Exception:
        return None


def get_forecast() -> Optional[dict]:
    """Cached forecast; falls back to stale data when a refresh fails. Never raises."""
    now = time.monotonic()
    fresh = (
        _forecast_cache["data"] is not None
        and now - _forecast_cache["at"] < FORECAST_TTL_S
    )
    if fresh:
        return _forecast_cache["data"]
    try:
        data = fetch_forecast()
    except Exception:
        data = None
    if data is not None:
        _forecast_cache["at"] = now
        _forecast_cache["data"] = data
        return data
    return _forecast_cache["data"]  # stale is better than nothing
