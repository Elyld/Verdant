"""🌙 Frost-night gamble — one bold call: COVER or HARVEST NOW.

Triggered when tonight's forecast low is ≤ 38°F, or the first fall frost is
within 3 days. Combines tonight's low with what's actually in the ground:
harvest-ready plants (ai_context's harvest-forecast pattern) and tender
plants (garden_alerts.is_tender) to make the call.

Advisory only — the verdict is phrased as a recommendation, never a command.
frost_verdict returns None when there's no frost risk, no weather data, or
nothing at stake. Never raises.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Optional

from sqlmodel import Session, select

from app import frost as frost_mod
from app import planting as planting_mod
from app import weather as weather_mod
from app.garden_alerts import is_tender
from app.models import Plant

# Tonight's low at or below this triggers the gamble.
FROST_TRIGGER_F = 38
# This counts as a hard freeze — covering won't reliably save tender plants.
HARD_FREEZE_F = 32
# First fall frost this many days out (or fewer) also triggers the gamble.
FROST_DAYS_OUT = 3
# Discord caps messages at 2000 chars; keep the digest block well under.
DIGEST_MAX_CHARS = 1200


def _tonights_low(session: Session) -> Optional[float]:
    """Tonight's forecast low in °F, or None when no forecast is available."""
    try:
        fc = weather_mod.get_forecast(session)
    except Exception:
        return None
    daily = (fc or {}).get("daily") or []
    if not daily:
        return None
    try:
        return float(daily[0].get("tmin_f"))
    except (TypeError, ValueError):
        return None


def _days_to_first_frost(session: Session, today: Date) -> Optional[int]:
    try:
        frost, _source, _zone = frost_mod.resolve_frost(session, "first", today=today)
    except Exception:
        return None
    if frost is None:
        return None
    return (frost - today).days


def _ready_and_tender(session: Session, today: Date) -> tuple[list[str], list[str]]:
    """(harvest-ready plant names, tender growing plant names)."""
    plants = session.exec(
        select(Plant).where(Plant.status == "Growing")
        .order_by(Plant.variety_name)).all()
    ready, tender = [], []
    for p in plants:
        try:
            planted = p.date_planted or p.date_started_indoors
            fc = planting_mod.harvest_forecast(
                p.variety_name, p.species_type, planted,
                p.days_to_maturity, today=today)
            if fc and fc.get("status") == "ready":
                ready.append(p.variety_name)
        except Exception:
            pass
        try:
            if is_tender(p):
                tender.append(p.variety_name)
        except Exception:
            pass
    return ready, tender


def frost_verdict(session: Session) -> Optional[dict]:
    """Make the frost call: {"verdict", "cover_list", "harvest_list", "reasoning"}.

    verdict is "COVER" or "HARVEST NOW". Returns None when there's no frost
    risk (or no forecast to judge by), or nothing in the garden is at stake.
    Advisory only; never raises.
    """
    today = Date.today()
    low = _tonights_low(session)
    days_to_frost = _days_to_first_frost(session, today)

    triggered = (
        (low is not None and low <= FROST_TRIGGER_F)
        or (days_to_frost is not None and 0 <= days_to_frost <= FROST_DAYS_OUT)
    )
    if not triggered:
        return None

    harvest_list, cover_list = _ready_and_tender(session, today)
    if not harvest_list and not cover_list:
        return None  # frost risk, but nothing tender or ripe — stay quiet

    hard_freeze = low is not None and low <= HARD_FREEZE_F

    if low is not None:
        weather_bit = f"Tonight's low is forecast around {round(low)}°F"
    elif days_to_frost is not None:
        weather_bit = (f"First fall frost is ~{days_to_frost} days out"
                       if days_to_frost > 0 else "First fall frost is expected today")
    else:
        weather_bit = "Frost risk is on the table tonight"

    if hard_freeze and harvest_list:
        verdict = "HARVEST NOW"
        reasoning = (
            f"{weather_bit} — a hard freeze that cold will kill tender plants outright "
            "no matter what. My call: pick everything ripe now rather than gamble "
            "on saving the plants."
        )
    elif cover_list:
        verdict = "COVER"
        if hard_freeze:
            reasoning = (
                f"{weather_bit} — that's a hard freeze, so covering is a gamble, "
                "not a guarantee. My call: cover the tender ones tonight and hope "
                "the coldest hours pass over them."
            )
        else:
            reasoning = (
                f"{weather_bit} — a light frost, which row cover or blankets usually "
                "beat. My call: cover the tender ones before bed and pick what's "
                "ripe in the morning."
            )
    else:
        # Light frost risk, ripe produce, nothing tender in the ground.
        verdict = "HARVEST NOW"
        reasoning = (
            f"{weather_bit} — frost can still nip ripe fruit. My call: pick what's "
            "ripe tonight; the plants themselves should be fine."
        )

    return {
        "verdict": verdict,
        "cover_list": cover_list,
        "harvest_list": harvest_list,
        "reasoning": reasoning,
    }


def digest_block(session: Session) -> Optional[str]:
    """Compact frost-call block for the morning digest, or None.

    The digest router calls this inside ``_message_with_extras``; the block
    stays well under Discord's 2000-char cap.
    """
    try:
        verdict = frost_verdict(session)
    except Exception:
        return None
    if not verdict:
        return None
    lines = [f"❄️ **Frost call: {verdict['verdict']}**"]
    if verdict["harvest_list"]:
        lines.append("Harvest: " + ", ".join(verdict["harvest_list"][:8]))
    if verdict["cover_list"]:
        lines.append("Cover: " + ", ".join(verdict["cover_list"][:8]))
    lines.append(f"_{verdict['reasoning']}_")
    block = "\n".join(lines)
    return block if len(block) <= DIGEST_MAX_CHARS else block[:DIGEST_MAX_CHARS - 1] + "…"
