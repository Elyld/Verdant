"""Weather API: cached forecast + garden alerts linked to the user's data."""
from __future__ import annotations

from datetime import date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app import frost as frost_mod
from app import garden_alerts, weather as weather_mod
from app.database import get_session

router = APIRouter(prefix="/api/weather", tags=["weather"])


def _temp_unit(session: Session) -> str:
    unit = frost_mod.get_setting(session, "temperature_unit") or "F"
    return unit if unit in ("F", "C") else "F"


def _convert(forecast: dict, unit: str) -> dict:
    """Forecast arrives in F; convert to C when the user prefers it."""
    if unit == "F":
        return forecast
    out = dict(forecast)
    out["current"] = dict(forecast.get("current") or {})

    def c(f):
        return round((f - 32) * 5 / 9, 1) if isinstance(f, (int, float)) else f

    if isinstance(out["current"].get("temp_f"), (int, float)):
        out["current"]["temp_f"] = c(out["current"]["temp_f"])
    out["hourly"] = [
        {**h, "temp_f": c(h.get("temp_f"))} for h in (forecast.get("hourly") or [])
    ]
    out["daily"] = [
        {**d, "tmax_f": c(d.get("tmax_f")), "tmin_f": c(d.get("tmin_f"))}
        for d in (forecast.get("daily") or [])
    ]
    return out


@router.get("/forecast")
def get_forecast(session: Session = Depends(get_session)) -> dict:
    if not weather_mod.configured():
        return {"ok": False, "reason": "not-configured",
                "hint": "Set GARDEN_LAT and GARDEN_LON to enable weather."}
    fc = weather_mod.get_forecast()
    if not fc:
        return {"ok": False, "reason": "unavailable",
                "hint": "Could not reach the forecast service."}
    unit = _temp_unit(session)
    return {"ok": True, "temp_unit": unit, "forecast": _convert(fc, unit)}


@router.get("/alerts")
def get_alerts(session: Session = Depends(get_session)) -> dict:
    if not weather_mod.configured():
        return {"ok": False, "reason": "not-configured", "alerts": []}
    fc = weather_mod.get_forecast()
    if not fc or not (fc.get("hourly") or []):
        return {"ok": False, "reason": "unavailable", "alerts": []}
    unit = _temp_unit(session)
    alerts = garden_alerts.compute_alerts(session, fc, today=date_cls.today(), temp_unit=unit)
    return {"ok": True, "temp_unit": unit, "as_of": fc.get("as_of"), "alerts": alerts}
