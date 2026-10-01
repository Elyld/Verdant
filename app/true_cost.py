"""True-cost verdict: was it cheaper than the grocery store?

Spend comes from the Expense table (the season scorecard's source —
invoice-derived expenses live there too since v2.21.0, so no double
counting). Per-variety spend attribution mirrors the scorecard; spend
that can't be tied to a plant is split proportionally by harvest weight
and labeled as such.
"""
from __future__ import annotations

from datetime import date as Date

from sqlmodel import Session, select

from app import units as units_mod
from app.models import Expense, Harvest, Plant
from app.routers.stats import season_scorecard

# Rough grocery-store prices, $/lb. Estimates — for fun, not accounting.
GROCERY_BASELINE: dict[str, float] = {
    "tomato": 2.50,
    "pepper": 3.00,
    "lettuce": 4.00,
    "cucumber": 1.75,
    "zucchini": 1.50,
    "carrot": 1.25,
    "bean": 3.50,
    "herb": 8.00,
}

DISCLAIMER = (
    "Grocery prices are rough estimates, not quotes — and they can't price "
    "the flavor of a tomato still warm from the sun. 🌱"
)


def _match_baseline(variety: str, species: str = "") -> tuple[str, float | None]:
    """Match a variety/species name to a grocery baseline by keyword.

    Returns (label, $/lb) or ("—", None) when nothing matches."""
    text = f"{variety or ''} {species or ''}".lower()
    for keyword, price in GROCERY_BASELINE.items():
        if keyword in text:
            return f"${price:.2f}/lb (est.)", price
    return "—", None


def true_cost_report(session: Session, year: int | None = None) -> dict:
    """True-cost verdict for a year. Never raises — returns a friendly
    empty report on failure."""
    try:
        if year is None:
            year = Date.today().year
        prefix = f"{year}-"
        scorecard = season_scorecard(year=year, session=session)

        by_id = {p.id: p for p in session.exec(select(Plant)).all()}

        # Reuse scorecard totals (they come from the Expense table, which
        # already includes invoice-derived expenses).
        total_spend = float(scorecard.get("total_spent", 0.0) or 0.0)

        per_variety = []
        total_harvest_oz = float(scorecard.get("total_oz", 0.0) or 0.0)
        weighed_oz = 0.0
        for row in scorecard.get("varieties", []):
            oz = float(row.get("total_oz", 0.0) or 0.0)
            if oz > 0:
                weighed_oz += oz

        for row in scorecard.get("varieties", []):
            variety = row.get("variety", "?")
            oz = float(row.get("total_oz", 0.0) or 0.0)
            direct = float(row.get("direct_cost", 0.0) or 0.0)
            # Attribute unassigned spend proportionally by harvest weight.
            unassigned = float(scorecard.get("unassigned_spent", 0.0) or 0.0)
            attributed = unassigned * (oz / weighed_oz) if weighed_oz > 0 else 0.0
            spend = direct + attributed
            harvest_lb = oz / 16.0
            per_lb = (spend / harvest_lb) if harvest_lb > 0 else None

            species = ""
            for p in by_id.values():
                if p.variety_name == variety:
                    species = p.species_type or ""
                    break
            baseline_label, baseline = _match_baseline(variety, species)
            if per_lb is None:
                verdict = "no weighed harvests logged"
            elif baseline is None:
                verdict = f"grew it for ${per_lb:.2f}/lb 🎉"
            elif per_lb < baseline:
                verdict = f"grew it for ${per_lb:.2f}/lb vs ${baseline:.2f} at the store 🎉"
            elif per_lb == baseline:
                verdict = f"grew it for ${per_lb:.2f}/lb — a wash with the store 🤝"
            else:
                verdict = (f"grew it for ${per_lb:.2f}/lb vs ${baseline:.2f} at the store — "
                           f"but you can't buy that freshness 🍅")

            per_variety.append(
                {
                    "variety": variety,
                    "harvest_lb": round(harvest_lb, 2),
                    "per_lb": round(per_lb, 2) if per_lb is not None else None,
                    "grocery_baseline": baseline_label,
                    "verdict": verdict,
                }
            )
        per_variety.sort(key=lambda r: (r["per_lb"] is None, r["per_lb"] or 0))

        total_harvest_lb = total_harvest_oz / 16.0
        overall = (total_spend / total_harvest_lb) if total_harvest_lb > 0 else None

        return {
            "year": year,
            "total_spend": round(total_spend, 2),
            "total_harvest_lb": round(total_harvest_lb, 2),
            "overall_per_lb": round(overall, 2) if overall is not None else None,
            "per_variety": per_variety,
            "disclaimer": DISCLAIMER,
            "has_data": bool(per_variety or total_spend),
            "attribution_note": (
                "Unassigned spending was split across varieties proportionally "
                "by harvest weight."
            ),
        }
    except Exception:
        return {
            "year": year or Date.today().year,
            "total_spend": 0.0,
            "total_harvest_lb": 0.0,
            "overall_per_lb": None,
            "per_variety": [],
            "disclaimer": DISCLAIMER,
            "has_data": False,
            "attribution_note": "",
        }
