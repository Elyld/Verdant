"""Current weather via Open-Meteo (free, no API key required).

Garden coordinates come from the Settings page (garden_lat / garden_lon),
with the GARDEN_LAT / GARDEN_LON env vars as fallback — Settings win, so a
stale env var can never shadow what was picked in the UI.
If unset, weather capture is skipped silently.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

from app import frost as frost_mod


def _parse_coords(lat_raw, lon_raw) -> Optional[tuple[float, float]]:
    """Parse a lat/lon pair; None when missing, non-numeric, or out of range."""
    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def _coords(session=None) -> Optional[tuple[float, float]]:
    """Garden coordinates. The Settings page (garden_lat/garden_lon) outranks
    the GARDEN_LAT/GARDEN_LON env vars; a partial or invalid Settings entry
    falls through to env rather than breaking weather."""
    if session is not None:
        pair = _parse_coords(
            frost_mod.get_setting(session, "garden_lat"),
            frost_mod.get_setting(session, "garden_lon"),
        )
        if pair is not None:
            return pair
    return _parse_coords(os.getenv("GARDEN_LAT", ""), os.getenv("GARDEN_LON", ""))


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


def fetch_current_weather(session=None) -> Optional[dict]:
    """Return {'temp_c': float, 'summary': str} or None if unavailable.

    Never raises: any failure (no coords, no network, bad payload) → None.
    """
    coords = _coords(session)
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


def configured(session=None) -> bool:
    return _coords(session) is not None


# --------------------------------------------------------------------------- #
# Forecast (hourly + daily), cached server-side so the UI stays fast.
# --------------------------------------------------------------------------- #
FORECAST_TTL_S = 1800  # 30 minutes
_forecast_cache = {"at": 0.0, "data": None}


def fetch_forecast(session=None) -> Optional[dict]:
    """Fetch and compact the Open-Meteo forecast. Never raises.

    Returns imperial units (F, mph, inches) — the router converts to C when
    the user's temperature_unit setting says so. Shape:
      {"as_of": iso, "current": {...}, "hourly": [...48], "daily": [...7]}
    """
    coords = _coords(session)
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
        "precipitation_sum,wind_gusts_10m_max,shortwave_radiation_sum"
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
        drad = dcol("shortwave_radiation_sum")
        days = [
            {
                "date": dtime[i],
                "tmax_f": dmax[i],
                "tmin_f": dmin[i],
                "precip_prob": dprob[i],
                "precip_in": dprecip[i],
                "gust_mph": dgust[i],
                "rad_mj": drad[i],  # measured solar radiation, MJ/m^2/day
            }
            for i in range(m)
        ]
        return {
            "as_of": current.get("time"),
            "elevation_m": payload.get("elevation"),
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


def get_forecast(session=None) -> Optional[dict]:
    """Cached forecast; falls back to stale data when a refresh fails. Never raises.

    The cache is keyed by coords, so changing the garden location in Settings
    refreshes immediately instead of serving the old spot's forecast.
    """
    coords = _coords(session)
    if coords is None:
        return None
    now = time.monotonic()
    fresh = (
        _forecast_cache["data"] is not None
        and _forecast_cache.get("coords") == coords
        and now - _forecast_cache["at"] < FORECAST_TTL_S
    )
    if fresh:
        return _forecast_cache["data"]
    try:
        data = fetch_forecast(session)
    except Exception:
        data = None
    if data is not None:
        _forecast_cache["at"] = now
        _forecast_cache["data"] = data
        _forecast_cache["coords"] = coords
        return data
    if _forecast_cache.get("coords") == coords:
        return _forecast_cache["data"]  # stale is better than nothing
    return None


# --------------------------------------------------------------------------- #
# NOAA / National Weather Service active alerts, cached server-side.
# Free, no key — but api.weather.gov requires a User-Agent header.
# --------------------------------------------------------------------------- #
NOAA_TTL_S = 900  # 15 minutes
_noaa_cache = {"at": 0.0, "data": None, "coords": None}


def _trim_noaa_alert(props: dict) -> dict:
    """Keep only what the ribbon panel needs."""
    desc = props.get("description") or ""
    if len(desc) > 600:
        desc = desc[:600].rsplit(" ", 1)[0] + "…"
    return {
        "event": props.get("event") or "Alert",
        "headline": props.get("headline") or "",
        "severity": props.get("severity") or "Unknown",
        "onset": props.get("onset"),
        "ends": props.get("ends"),
        "description": desc,
    }


def fetch_noaa_alerts(session=None) -> Optional[list]:
    """Fetch active NWS alerts for the garden point. Never raises.

    Returns a trimmed list of dicts; [] when coords are unconfigured or
    genuinely no alerts are active; None when the fetch itself failed
    (so callers can keep serving stale data instead of blanking).
    """
    coords = _coords(session)
    if coords is None:
        return []
    lat, lon = coords
    url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "verdant-garden-log", "Accept": "application/geo+json"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        features = payload.get("features") or []
        return [_trim_noaa_alert(f.get("properties") or {}) for f in features]
    except Exception:
        return None


def get_noaa_alerts(session=None) -> list:
    """Cached NOAA alerts, keyed by coords. Never raises; stale data is
    served when a refresh fails so a blip doesn't blank the ribbon."""
    coords = _coords(session)
    if coords is None:
        return []
    now = time.monotonic()
    fresh = (
        _noaa_cache["data"] is not None
        and _noaa_cache.get("coords") == coords
        and now - _noaa_cache["at"] < NOAA_TTL_S
    )
    if fresh:
        return _noaa_cache["data"]
    try:
        data = fetch_noaa_alerts(session)
    except Exception:
        data = None
    if data is not None:
        _noaa_cache["at"] = now
        _noaa_cache["data"] = data
        _noaa_cache["coords"] = coords
        return data
    if _noaa_cache.get("coords") == coords:
        return _noaa_cache["data"] or []  # stale is better than nothing
    return []
