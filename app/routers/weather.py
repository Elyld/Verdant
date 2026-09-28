"""Weather API: cached forecast + garden alerts linked to the user's data."""
from __future__ import annotations

import json
import urllib.request
from datetime import date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app import frost as frost_mod
from app import garden_alerts, weather as weather_mod
from app.database import get_session

router = APIRouter(prefix="/api/weather", tags=["weather"])

NOT_CONFIGURED_HINT = (
    "Set your garden coordinates on the Settings page "
    "(or the GARDEN_LAT / GARDEN_LON env vars) to enable weather."
)


def _temp_unit(session: Session) -> str:
    unit = frost_mod.get_setting(session, "temperature_unit") or "F"
    return unit if unit in ("F", "C") else "F"


def _convert(forecast: dict, unit: str) -> dict:
    """Forecast arrives in F; convert to C when the user prefers it.

    Converted payloads use _c key names — the old _f keys holding Celsius
    values were a trap for every future consumer.
    """
    if unit == "F":
        return forecast
    out = dict(forecast)
    current = dict(forecast.get("current") or {})

    def c(f):
        return round((f - 32) * 5 / 9, 1) if isinstance(f, (int, float)) else f

    if isinstance(current.get("temp_f"), (int, float)):
        current["temp_c"] = c(current.pop("temp_f"))
    out["current"] = current
    hourly = []
    for h in forecast.get("hourly") or []:
        h = dict(h)
        if isinstance(h.get("temp_f"), (int, float)):
            h["temp_c"] = c(h.pop("temp_f"))
        hourly.append(h)
    out["hourly"] = hourly
    daily = []
    for d in forecast.get("daily") or []:
        d = dict(d)
        if isinstance(d.get("tmax_f"), (int, float)):
            d["tmax_c"] = c(d.pop("tmax_f"))
        if isinstance(d.get("tmin_f"), (int, float)):
            d["tmin_c"] = c(d.pop("tmin_f"))
        daily.append(d)
    out["daily"] = daily
    return out


@router.get("/forecast")
def get_forecast(session: Session = Depends(get_session)) -> dict:
    if not weather_mod.configured(session):
        return {"ok": False, "reason": "not-configured",
                "hint": NOT_CONFIGURED_HINT}
    fc = weather_mod.get_forecast(session)
    if not fc:
        return {"ok": False, "reason": "unavailable",
                "hint": "Could not reach the forecast service."}
    unit = _temp_unit(session)
    return {"ok": True, "temp_unit": unit, "forecast": _convert(fc, unit)}


@router.get("/alerts")
def get_alerts(session: Session = Depends(get_session)) -> dict:
    if not weather_mod.configured(session):
        return {"ok": False, "reason": "not-configured", "alerts": []}
    fc = weather_mod.get_forecast(session)
    if not fc or not (fc.get("hourly") or []):
        return {"ok": False, "reason": "unavailable", "alerts": []}
    unit = _temp_unit(session)
    alerts = garden_alerts.compute_alerts(session, fc, today=date_cls.today(), temp_unit=unit)
    return {"ok": True, "temp_unit": unit, "as_of": fc.get("as_of"), "alerts": alerts}


@router.get("/geolocate")
def geolocate() -> dict:
    """One-shot IP-based location lookup for the Settings page's
    \"Use my location\" button. City-level accuracy via ip-api.com (free, no
    key). Click-only — never called in the background — and nothing is
    stored; the button just fills the latitude/longitude fields for the user
    to save. Never raises: any failure → {"ok": False}.
    """
    try:
        request = urllib.request.Request(
            "https://ip-api.com/json/?fields=status,lat,lon,city",
            headers={"User-Agent": "verdant-garden-log"},
        )
        with urllib.request.urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") != "success":
            return {"ok": False, "reason": "lookup-failed"}
        return {
            "ok": True,
            "lat": float(payload["lat"]),
            "lon": float(payload["lon"]),
            "city": payload.get("city") or "",
        }
    except Exception:
        return {"ok": False, "reason": "lookup-failed"}
