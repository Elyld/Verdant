"""Compact garden context for the chat assistant.

One plain-text block (~1k tokens max) summarizing what the assistant needs
to answer "how are my tomatoes doing?" without inventing anything: growing
plants and where they live, what's due, what's ready to harvest, recent
activity, weather, and the frost countdown. Truncated aggressively — this
rides along on every chat call, and on OpenRouter every token costs money.
"""
from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

from sqlmodel import Session, select

from app.models import (
    Container,
    FertilizationLog,
    Harvest,
    ObservationLog,
    Plant,
    Planting,
    WateringLog,
)

MAX_PLANTS = 40
MAX_ITEMS = 8


def _recent_counts(session: Session, since_iso: str) -> str:
    parts = []
    waters = session.exec(
        select(WateringLog).where(WateringLog.date >= since_iso)).all()
    if waters:
        parts.append(f"{len(waters)} waterings")
    feeds = session.exec(
        select(FertilizationLog).where(FertilizationLog.date >= since_iso)).all()
    if feeds:
        parts.append(f"{len(feeds)} feedings")
    harvests = session.exec(
        select(Harvest).where(Harvest.date >= since_iso)).all()
    if harvests:
        qty = sum(h.quantity or 0 for h in harvests)
        parts.append(f"{len(harvests)} harvests ({qty} items)")
    notes = session.exec(
        select(ObservationLog).where(ObservationLog.date >= since_iso)).all()
    if notes:
        parts.append(f"{len(notes)} notes")
    return ", ".join(parts) if parts else "nothing logged"


def build_context(session: Session) -> str:
    """Assemble the context block. Never raises — a thin context beats a 500."""
    from app import frost as frost_mod
    from app.routers.plants import plant_reminders

    today = Date.today()
    lines = [f"Today is {today.strftime('%A, %B %d, %Y')}."]

    zone = frost_mod.get_setting(session, "zone") or "?"
    lines.append(f"USDA zone: {zone}.")

    # Frost countdown
    try:
        frost, _source, _z = frost_mod.resolve_frost(session, "first", today=today)
        if frost:
            days = (frost - today).days
            lines.append(
                f"First fall frost: {frost.isoformat()} ({days} days away)."
                if days >= 0 else
                f"First fall frost was {frost.isoformat()} ({-days} days ago)."
            )
    except Exception:
        pass

    # Growing plants + where they live (this season's plantings)
    try:
        plants = session.exec(
            select(Plant).where(Plant.status == "Growing")
            .order_by(Plant.variety_name).limit(MAX_PLANTS)).all()
        plantings = session.exec(
            select(Planting).where(Planting.season_year == today.year)).all()
        homes: dict[int, list[str]] = {}
        for pl in plantings:
            if pl.plant_id is not None:
                homes.setdefault(pl.plant_id, []).append(
                    (pl.container.name if pl.container else None) or f"container #{pl.container_id}")
        if plants:
            bits = []
            for p in plants:
                bit = f"{p.variety_name} ({p.species_type})"
                if p.id in homes:
                    bit += f" in {', '.join(homes[p.id][:2])}"
                if p.date_planted:
                    bit += f", planted {p.date_planted.isoformat()}"
                bits.append(bit)
            lines.append(f"Growing ({len(plants)}): " + "; ".join(bits) + ".")
        else:
            lines.append("Growing: no plants currently marked Growing.")
    except Exception:
        pass

    # What's due
    try:
        reminders = plant_reminders(session)
        due = [r for r in reminders if r.status in ("overdue", "due")][:MAX_ITEMS]
        if due:
            bits = []
            for r in due:
                bit = f"{r.kind} {r.plant_name} ({r.status}"
                if r.status == "overdue" and (r.days_until_due or 0) < 0:
                    bit += f" {-r.days_until_due}d"
                bits.append(bit + ")")
            lines.append("Due now: " + "; ".join(bits) + ".")
        else:
            lines.append("Due now: nothing overdue or due.")
    except Exception:
        pass

    # Ready to harvest (planted date + maturity timing)
    try:
        from app import planting as planting_mod

        ready = []
        for p in plants or []:
            planted = p.date_planted or p.date_started_indoors
            fc = planting_mod.harvest_forecast(
                p.variety_name, p.species_type, planted,
                p.days_to_maturity, today=today)
            if fc and fc.get("status") == "ready":
                ready.append(p.variety_name)
            if len(ready) >= MAX_ITEMS:
                break
        if ready:
            lines.append("Ready to harvest now: " + ", ".join(ready) + ".")
    except Exception:
        pass

    # Recent activity
    try:
        since_iso = (today - timedelta(days=14)).isoformat()
        lines.append(f"Last 14 days: {_recent_counts(session, since_iso)}.")
        last_harvests = session.exec(
            select(Harvest).order_by(Harvest.date.desc()).limit(3)).all()
        if last_harvests:
            bits = []
            for h in last_harvests:
                name = (h.plant.variety_name if h.plant else None) or "?"
                bits.append(f"{h.quantity or '?'}x {name} on {h.date}")
            lines.append("Latest harvests: " + "; ".join(bits) + ".")
    except Exception:
        pass

    # Per-plant care history — the "when did I last feed the tomatoes?" answer.
    try:
        growing = session.exec(
            select(Plant).where(Plant.status == "Growing")
            .order_by(Plant.variety_name).limit(MAX_PLANTS)).all()
        hist_lines = []
        for p in growing:
            w = session.exec(
                select(WateringLog).where(WateringLog.plant_id == p.id)
                .order_by(WateringLog.date.desc()).limit(1)).first()
            f = session.exec(
                select(FertilizationLog).where(FertilizationLog.plant_id == p.id)
                .order_by(FertilizationLog.date.desc()).limit(1)).first()
            h = session.exec(
                select(Harvest).where(Harvest.plant_id == p.id)
                .order_by(Harvest.date.desc()).limit(1)).first()
            bits = []
            bits.append(f"watered {w.date}" if w and w.date else "never watered")
            if f and f.date:
                prod = (f.fertilizer_name or "").strip()
                bits.append(f"fed {f.date}" + (f" ({prod})" if prod else ""))
            else:
                bits.append("never fed")
            if h and h.date:
                bits.append(f"harvested {h.date} ({h.quantity or '?'}x)")
            else:
                bits.append("never harvested")
            hist_lines.append(f"- {p.variety_name}: " + " · ".join(bits))
        if hist_lines:
            lines.append("Care history (most recent per plant):\n" + "\n".join(hist_lines))
    except Exception:
        pass

    # Weather, when configured
    try:
        lat = (frost_mod.get_setting(session, "garden_lat") or "").strip()
        if lat:
            from app import weather as weather_mod

            fc = weather_mod.get_forecast(session)
            current = (fc or {}).get("current") or {}
            daily = (fc or {}).get("daily") or []
            d0 = daily[0] if daily else {}
            if current.get("temp_f") is not None:
                lines.append(
                    f"Weather now: {round(current['temp_f'])}°F; "
                    f"today's high {round(d0.get('tmax_f') or 0)}°F, "
                    f"{d0.get('precip_prob') or 0}% rain.")
    except Exception:
        pass

    return "\n".join(lines)
