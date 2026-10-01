"""Plant autopsy helpers (wild-ideas track).

A plant autopsy is stored as an ObservationLog note whose text starts with
the "💀 Autopsy — " marker — no new table, no new draft action. The write
tool `record_autopsy` maps to the existing "note" draft action in
WRITE_TOOL_ACTIONS, so the gardener confirms it in the UI exactly like any
other note and confirmDrafts needs no frontend change.

The scan helpers below feed autopsy deaths into `variety_performance` (see
the integration spec for the exact patch against `_t_variety_performance`).
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

#: Marker prefixing every autopsy note. The trailing em dash is part of the
#: marker — compose/parse/scan all build from this constant so they can't drift.
AUTOPSY_MARKER = "💀 Autopsy — "


def compose_autopsy_note(variety: str, cause: str, extra: str = "") -> str:
    """Build the note text for an autopsy draft.

    Format: "💀 Autopsy — {variety}: {cause}.{extra}"
    """
    variety = (variety or "").strip()
    cause = (cause or "").strip()
    text = f"{AUTOPSY_MARKER}{variety}: {cause}."
    extra = (extra or "").strip()
    if extra:
        text += f" {extra}"
    return text


def parse_autopsy_note(text: str) -> tuple[Optional[str], str]:
    """Split "💀 Autopsy — {variety}: {rest}" into (variety, rest).

    Returns (None, body) when the note has no "variety: " prefix.
    """
    body = (text or "")
    if body.startswith(AUTOPSY_MARKER):
        body = body[len(AUTOPSY_MARKER):]
    variety, sep, rest = body.partition(": ")
    if not sep:
        return None, body.strip()
    variety = variety.strip()
    return (variety or None), rest.strip()


def resolve_autopsy_args(session: Session, plant: str, cause: str,
                         extra: str = "") -> Optional[dict]:
    """Turn record_autopsy params into args for the existing "note" draft flow.

    Fuzzy-matches the plant with the same helper the other write tools use;
    when no plant matches, the raw name goes in and the composed note carries
    it (same as other tools do). Returns None when required params are missing.
    """
    from app import ai_tools as ai_tools_mod

    cause = (cause or "").strip()
    name = (plant or "").strip()
    if not name or not cause:
        return None
    p = ai_tools_mod._match_plant(session, name)
    variety = p.variety_name if p else name
    return {"plant": variety, "note": compose_autopsy_note(variety, cause, extra)}


def autopsy_deaths_by_variety(session: Session) -> dict[str, list[str]]:
    """Scan ObservationLog for autopsy notes, grouped by variety.

    Each entry is "died {year}: {cause…}" — attached to variety_performance
    entries via attach_deaths() in the integration spec's patch.
    """
    from sqlmodel import select

    from app.models import ObservationLog

    rows = session.exec(
        select(ObservationLog).where(ObservationLog.notes.like(f"{AUTOPSY_MARKER}%"))
    ).all()
    out: dict[str, list[str]] = {}
    for n in rows:
        variety, rest = parse_autopsy_note(n.notes or "")
        variety = variety or (n.plant_name or "").strip() or "Unknown"
        year = (n.date or "")[:4] or "unknown"
        out.setdefault(variety, []).append(f"died {year}: {rest}")
    return out


def attach_deaths(variety_entries: list[dict], deaths: dict[str, list[str]]) -> None:
    """Attach per-variety death notes onto variety_performance-style entries.

    Mutates the entries in place: existing varieties gain a "notes" list;
    varieties that died before ever harvesting are appended with zero totals.
    """
    known = {v["variety"]: v for v in variety_entries}
    for variety, causes in deaths.items():
        entry = known.get(variety)
        if entry is None:
            entry = {"variety": variety, "years": {},
                     "total_harvests": 0, "total_quantity": 0}
            variety_entries.append(entry)
            known[variety] = entry
        entry["notes"] = sorted(causes)
