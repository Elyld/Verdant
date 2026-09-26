"""Garden alerts: link the weather forecast to the user's real garden data.

Each alert names the actual plants and containers it affects — a frost warning
is only useful if it says *which* peppers are in the ground. Pure functions
over (session, forecast) so they're easy to test.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlmodel import Session, desc

from app.models import Container, PestLog, Plant, Planting, WateringLog

# Plants that can't take frost, matched against variety/species/family text.
TENDER_KEYWORDS = {
    "solanaceae", "capsicum", "pepper", "chili", "chile",
    "solanum lycopersicum", "tomato",
    "cucurbitaceae", "cucumber", "cucumis", "squash", "cucurbita",
    "zucchini", "melon", "citrullus", "cucumis melo",
    "basil", "ocimum",
    "bean", "phaseolus",
    "corn", "zea mays",
    "eggplant", "solanum melongena",
    "okra", "abelmoschus",
    "sweet potato", "ipomoea batatas",
}

# Container kinds that dry out fast in heat.
THIRSTY_KINDS = {"pot", "grow bag", "planter"}


def _plant_text(plant: Plant) -> str:
    return " ".join([
        plant.variety_name or "",
        plant.species_type or "",
        plant.family_genus or "",
    ]).lower()


def is_tender(plant: Plant) -> bool:
    text = _plant_text(plant)
    return any(kw in text for kw in TENDER_KEYWORDS)


def _season_plantings(session: Session, year: int):
    """(planting, plant, container) for a season, skipping orphans."""
    rows = (
        session.query(Planting, Plant, Container)
        .join(Plant, Planting.plant_id == Plant.id)
        .join(Container, Planting.container_id == Container.id)
        .filter(Planting.season_year == year)
        .all()
    )
    return rows


def _parse_day(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _recent_dates(session: Session, model, days: int, today: date, date_col="date"):
    """Newest log dates within the last `days` days (ISO strings compare fine)."""
    cutoff = (today - timedelta(days=days)).isoformat()
    rows = (
        session.query(model)
        .filter(getattr(model, date_col) >= cutoff)
        .order_by(desc(getattr(model, date_col)))
        .all()
    )
    return rows


def _min_temp_48h(forecast: dict) -> Optional[float]:
    temps = [h.get("temp_f") for h in (forecast.get("hourly") or [])[:48]]
    temps = [t for t in temps if isinstance(t, (int, float))]
    return min(temps) if temps else None


def _max_temp_48h(forecast: dict) -> Optional[float]:
    temps = [h.get("temp_f") for h in (forecast.get("hourly") or [])[:48]]
    temps = [t for t in temps if isinstance(t, (int, float))]
    return max(temps) if temps else None


def _precip_24h(forecast: dict) -> float:
    vals = [h.get("precip_in") or 0 for h in (forecast.get("hourly") or [])[:24]]
    return round(sum(v for v in vals if isinstance(v, (int, float))), 2)


def _max_gust_24h(forecast: dict) -> Optional[float]:
    vals = [h.get("gust_mph") for h in (forecast.get("hourly") or [])[:24]]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return max(vals) if vals else None


def _fmt_temp(f: float, unit: str) -> str:
    if unit == "C":
        return f"{round((f - 32) * 5 / 9)}°C"
    return f"{round(f)}°F"


def compute_alerts(
    session: Session,
    forecast: dict,
    today: Optional[date] = None,
    temp_unit: str = "F",
) -> list:
    """Build weather alerts tied to the garden's actual plants and containers."""
    today = today or date.today()
    year = today.year
    alerts = []

    hours = forecast.get("hourly") or []
    if not hours:
        return alerts

    plantings = _season_plantings(session, year)
    tender = [(p, pl, c) for (p, pl, c) in plantings if is_tender(pl)]
    tender_containers = sorted({c.name for (_, _, c) in tender if c.name})

    # -- frost ---------------------------------------------------------------
    low = _min_temp_48h(forecast)
    if low is not None and low <= 36 and tender:
        level = "critical" if low <= 32 else "warn"
        names = ", ".join(tender_containers[:3])
        more = f" (+{len(tender_containers) - 3} more)" if len(tender_containers) > 3 else ""
        alerts.append({
            "level": level,
            "icon": "🥶",
            "title": f"Frost risk — low of {_fmt_temp(low, temp_unit)} in the next 48h",
            "detail": (
                f"Tender plants are out: {names}{more}. "
                "Grow bags and pots lose heat faster than beds — cover them or move them in."
            ),
        })

    # -- heat ----------------------------------------------------------------
    high = _max_temp_48h(forecast)
    if high is not None and high >= 95:
        thirsty = sorted({
            c.name for (_, _, c) in plantings
            if (c.kind or "") in THIRSTY_KINDS and c.name
        })
        detail = (
            f"High of {_fmt_temp(high, temp_unit)} coming. "
            "Pots and grow bags dry out fast in this — water early in the morning."
        )
        if thirsty:
            detail += f" Thirstiest: {', '.join(thirsty[:3])}."
        alerts.append({
            "level": "warn", "icon": "🥵",
            "title": f"Heat stress — {_fmt_temp(high, temp_unit)} in the next 48h",
            "detail": detail,
        })

    # -- rain: skip watering ---------------------------------------------------
    rain = _precip_24h(forecast)
    watered = _recent_dates(session, WateringLog, 2, today)
    if rain >= 0.25 and watered:
        last = _parse_day(max(w.date or "" for w in watered))
        when = f" on {last.isoformat()}" if last else ""
        alerts.append({
            "level": "info", "icon": "🌧️",
            "title": f"{rain}″ rain expected in the next 24h — skip watering",
            "detail": f"You watered{when}. Let the sky do it today.",
        })

    # -- spray wash-off ---------------------------------------------------------
    rain12 = round(sum(
        (h.get("precip_in") or 0) for h in hours[:12]
        if isinstance(h.get("precip_in"), (int, float))
    ), 2)
    treated = [p for p in _recent_dates(session, PestLog, 3, today) if (p.treatment or "").strip()]
    if rain12 >= 0.3 and treated:
        latest = treated[0]
        plant = session.get(Plant, latest.plant_id) if latest.plant_id else None
        what = plant.variety_name if plant else (latest.pest_name or "a plant")
        alerts.append({
            "level": "warn", "icon": "🧪",
            "title": f"Rain will wash off that {latest.treatment} treatment",
            "detail": (
                f"{rain12}″ expected in the next 12h and you treated {what} "
                f"on {latest.date[:10]}. Plan a re-application after it passes."
            ),
        })

    # -- wind -------------------------------------------------------------------
    gust = _max_gust_24h(forecast)
    if gust is not None and gust >= 30:
        arch_names = sorted({
            c.name for (_, _, c) in plantings
            if (c.kind or "") == "arch" and c.name
        })
        detail = f"Gusts to {round(gust)} mph in the next 24h."
        if arch_names:
            detail += f" Check the stakes on: {', '.join(arch_names)}."
        else:
            detail += " Stake anything tall and check the arch."
        alerts.append({
            "level": "warn", "icon": "💨",
            "title": f"High wind — gusts to {round(gust)} mph",
            "detail": detail,
        })

    # -- disease pressure (tomatoes + warm humid nights) --------------------------
    tomato_out = any(
        any(kw in _plant_text(pl) for kw in ("tomato", "solanum lycopersicum"))
        for (_, pl, _) in plantings
    )
    humid_hours = [
        h for h in hours[:24]
        if isinstance(h.get("temp_f"), (int, float)) and h["temp_f"] >= 70
        and isinstance(h.get("rh"), (int, float)) and h["rh"] >= 85
    ]
    if tomato_out and len(humid_hours) >= 4:
        alerts.append({
            "level": "info", "icon": "🍅",
            "title": "Blight-friendly weather tonight",
            "detail": (
                "Warm and humid for hours overnight — prime early-blight conditions. "
                "Check the tomato leaves in the morning and water at the base, not overhead."
            ),
        })

    return alerts
