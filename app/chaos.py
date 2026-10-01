"""🎲 Chaos garden pick — one random experimental plant per year, outside the
gardener's comfort zone. No LLM needed: pre-written pitches, works offline.

The year's pick is stored in settings as JSON under ``chaos_pick_<year>``::

    {"variety": ..., "pitch": ..., "kind": ...,
     "picked_at": "ISO date", "accepted": bool, "rerolled": [variety, ...]}

History exclusion: anything the gardener has grown before (plants, plantings,
harvest logs, seed stash) plus every prior year's chaos pick is ineligible,
so the pick is always something new.
"""
import json
import random
from datetime import date
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session
from sqlmodel import select

# Each entry: name, one-line pitch (the app's voice), kind for display,
# and match keywords for history exclusion (lowercased, lenient substring).
CHAOS_VARIETIES: List[Dict[str, Any]] = [
    {"name": "Kohlrabi",
     "pitch": "Cabbage's weird alien cousin. Crunchy, sweet, ready in 55 days — great raw or roasted.",
     "kind": "Brassica", "match": ["kohlrabi"]},
    {"name": "Cucamelon",
     "pitch": "Grape-sized cucumbers that taste like lime. Kids go feral for them.",
     "kind": "Gourd", "match": ["cucamelon", "mouse melon", "melothria"]},
    {"name": "Ground Cherry",
     "pitch": "Pineapple-flavored candy in a paper lantern. Self-seeds like it pays rent.",
     "kind": "Fruit", "match": ["ground cherry", "husk cherry", "physalis"]},
    {"name": "Luffa",
     "pitch": "Grow your own shower sponges. Edible young, sponges later — two hobbies, one vine.",
     "kind": "Gourd", "match": ["luffa", "loofah", "sponge gourd"]},
    {"name": "Salsify",
     "pitch": "The oyster plant — tastes faintly of oysters. Nobody believes it until they try it.",
     "kind": "Root", "match": ["salsify"]},
    {"name": "Scorzonera",
     "pitch": "Salsify's goth sibling. Black skin, sweet white flesh, shrugs off cold.",
     "kind": "Root", "match": ["scorzonera", "black salsify"]},
    {"name": "Crosne",
     "pitch": "Tiny crunchy tubers that look like grubs. Plant once, dig 'em up for years.",
     "kind": "Root", "match": ["crosne", "chinese artichoke"]},
    {"name": "Sunchokes",
     "pitch": "Sunflower that makes tubers. Nutty, sweet, unstoppable — give it its own corner.",
     "kind": "Root", "match": ["sunchoke", "jerusalem artichoke"]},
    {"name": "Cardoon",
     "pitch": "Artichoke's dramatic 6-foot cousin. Blanched stalks taste like artichoke hearts.",
     "kind": "Perennial", "match": ["cardoon"]},
    {"name": "Lovage",
     "pitch": "Perennial celery on steroids. One plant replaces a whole celery patch.",
     "kind": "Herb", "match": ["lovage"]},
    {"name": "Orach",
     "pitch": "Spinach that doesn't bolt the second it gets warm. Red and purple — gorgeous.",
     "kind": "Green", "match": ["orach", "mountain spinach"]},
    {"name": "Agretti",
     "pitch": "Italian 'monk's beard.' Salty-crunchy greens — the trendy chef vegetable.",
     "kind": "Green", "match": ["agretti", "barba di frate", "salsola"]},
    {"name": "Malabar Spinach",
     "pitch": "Spinach for people whose spinach bolts. Heat-loving vine with thick glossy leaves.",
     "kind": "Green", "match": ["malabar"]},
    {"name": "New Zealand Spinach",
     "pitch": "Not spinach, doesn't care. Thrives in heat where real spinach gives up.",
     "kind": "Green", "match": ["new zealand spinach", "tetragonia"]},
    {"name": "Good King Henry",
     "pitch": "Perennial spinach-asparagus. Plant once, harvest for a decade.",
     "kind": "Perennial", "match": ["good king henry"]},
    {"name": "Claytonia",
     "pitch": "Miner's lettuce — cold-hardy salad green that grows when nothing else will.",
     "kind": "Green", "match": ["claytonia", "miner's lettuce"]},
    {"name": "Scarlet Runner Beans",
     "pitch": "Hummingbird magnets with beans you can actually eat. Insane red flowers.",
     "kind": "Bean", "match": ["runner bean", "scarlet runner"]},
    {"name": "Fava Beans",
     "pitch": "The original bean. Plant early; big buttery beans worth shelling.",
     "kind": "Bean", "match": ["fava", "broad bean"]},
    {"name": "Yardlong Beans",
     "pitch": "Beans that grow 3 feet long. Absurd, prolific, great stir-fried.",
     "kind": "Bean", "match": ["yardlong", "asparagus bean"]},
    {"name": "Edamame",
     "pitch": "Fresh soybeans from your own backyard. Eaten like candy, gone in minutes.",
     "kind": "Bean", "match": ["edamame", "soybean"]},
    {"name": "Bitter Melon",
     "pitch": "Wrinkly, bitter, beloved across Asia. An acquired taste worth acquiring.",
     "kind": "Gourd", "match": ["bitter melon", "bitter gourd"]},
    {"name": "Tinda",
     "pitch": "Apple-sized Indian squash, mild and versatile. Something new for the grill.",
     "kind": "Gourd", "match": ["tinda"]},
    {"name": "Papalo",
     "pitch": "Cilantro that laughs at heat. Pungent, citrusy, made for tacos.",
     "kind": "Herb", "match": ["papalo"]},
    {"name": "Shiso",
     "pitch": "Japanese basil's funky cousin. Wraps sushi, brightens everything.",
     "kind": "Herb", "match": ["shiso", "perilla"]},
    {"name": "Epazote",
     "pitch": "The bean herb. A pinch in the pot and the beans behave themselves.",
     "kind": "Herb", "match": ["epazote"]},
    {"name": "Anise Hyssop",
     "pitch": "Licorice-mint flowers that bees fight over. Makes a killer tea.",
     "kind": "Herb", "match": ["anise hyssop", "agastache"]},
    {"name": "Stevia",
     "pitch": "Grow your own sweetener. Absurdly sweet leaves, zero calories.",
     "kind": "Herb", "match": ["stevia"]},
    {"name": "Celeriac",
     "pitch": "The ugliest vegetable in the store is secretly delicious. Roast it whole.",
     "kind": "Root", "match": ["celeriac", "celery root"]},
    {"name": "Hamburg Parsley",
     "pitch": "Parsley that grows a parsnip-like root. Two crops, one plant.",
     "kind": "Root", "match": ["hamburg parsley", "root parsley"]},
    {"name": "Parsnip",
     "pitch": "Carrots with a graduate degree. Sweet after frost — leave some in the ground.",
     "kind": "Root", "match": ["parsnip"]},
    {"name": "Horseradish",
     "pitch": "Plant once, grate fresh forever. Aggressive — give it a buried pot.",
     "kind": "Perennial", "match": ["horseradish"]},
    {"name": "Walking Onions",
     "pitch": "Onions that plant themselves. Perpetual-motion scallions, zero effort.",
     "kind": "Perennial", "match": ["walking onion", "egyptian onion"]},
]


def _key(year: int) -> str:
    return f"chaos_pick_{year}"


def _read_raw(session: Session, year: int) -> Optional[dict]:
    from app.frost import get_setting

    raw = get_setting(session, _key(year))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _write_raw(session: Session, year: int, data: dict) -> None:
    from app.frost import set_setting

    set_setting(session, _key(year), json.dumps(data))
    session.commit()


def grown_names(session: Session) -> Set[str]:
    """Every variety name the gardener has grown: plants, plantings, harvest
    logs, and the seed stash — lowercased for lenient matching."""
    from app.models import Harvest, Plant, Planting, SeedPacket

    names: Set[str] = set()
    for p in session.exec(select(Plant)).all():
        if p.variety_name:
            names.add(p.variety_name.strip().lower())
    for h in session.exec(select(Harvest)).all():
        v = (h.plant.variety_name if h.plant else None)
        if v:
            names.add(v.strip().lower())
    for pl in session.exec(select(Planting)).all():
        v = (pl.plant.variety_name if pl.plant else None)
        if v:
            names.add(v.strip().lower())
    for sp in session.exec(select(SeedPacket)).all():
        if sp.variety_name:
            names.add(sp.variety_name.strip().lower())
    return {n for n in names if n}


def prior_chaos_picks(session: Session) -> Set[str]:
    """Varieties already used as chaos picks in ANY year (current pick +
    every reroll), so no year ever repeats another."""
    from app.models import Setting

    used: Set[str] = set()
    rows = session.exec(
        select(Setting).where(Setting.key.like("chaos_pick_%"))).all()
    for row in rows:
        try:
            data = json.loads(row.value or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("variety"):
            used.add(str(data["variety"]).strip().lower())
        for r in data.get("rerolled") or []:
            used.add(str(r).strip().lower())
    return used


def _matches_history(entry: dict, grown: Set[str]) -> bool:
    for kw in entry.get("match") or []:
        kw = kw.lower()
        if len(kw) < 4:
            continue
        for name in grown:
            if kw in name or (len(name) >= 4 and name in kw):
                return True
    # Also match the entry's own name words against history.
    for word in str(entry.get("name", "")).lower().split():
        if len(word) < 4:
            continue
        for name in grown:
            if word in name or (len(name) >= 4 and name in word):
                return True
    return False


def eligible_varieties(session: Session, exclude: Set[str] | None = None) -> List[dict]:
    """Chaos candidates: not grown before, not a prior chaos pick,
    not in the extra exclusion set. Falls back to the full list (minus
    this year's used) when exclusions would leave nothing."""
    grown = grown_names(session)
    used = prior_chaos_picks(session)
    extra = {e.strip().lower() for e in (exclude or set()) if e}
    eligible = [
        e for e in CHAOS_VARIETIES
        if not _matches_history(e, grown)
        and e["name"].strip().lower() not in used
        and e["name"].strip().lower() not in extra
    ]
    if not eligible:
        # Graceful fallback: anything not already used this year.
        eligible = [e for e in CHAOS_VARIETIES
                    if e["name"].strip().lower() not in extra]
    return eligible or list(CHAOS_VARIETIES)


def _pick_payload(entry: dict, accepted: bool = False,
                  rerolled: Optional[List[str]] = None) -> dict:
    return {"variety": entry["name"], "pitch": entry["pitch"],
            "kind": entry.get("kind", ""),
            "picked_at": date.today().isoformat(), "accepted": accepted,
            "rerolled": list(rerolled or [])}


def draw_initial(session: Session, year: int) -> dict:
    """Deterministic first draw for a year (seeded by year), persisted."""
    eligible = eligible_varieties(session)
    entry = random.Random(year).choice(eligible)
    payload = _pick_payload(entry)
    _write_raw(session, year, payload)
    return payload


def current_pick(session: Session, year: Optional[int] = None) -> dict:
    """This year's pick; draws (and persists) one when none exists."""
    year = year or date.today().year
    stored = _read_raw(session, year)
    if stored and stored.get("variety"):
        return {"year": year, **stored}
    return {"year": year, **draw_initial(session, year)}


def preview_reroll(session: Session, year: Optional[int] = None) -> dict:
    """What the next reroll WOULD draw — without persisting anything.
    Used by the chat confirm flow so the gardener sees the exact pick
    before it replaces the current one."""
    year = year or date.today().year
    stored = _read_raw(session, year) or {}
    rerolled = list(stored.get("rerolled") or [])
    if stored.get("variety"):
        rerolled.append(stored["variety"])
    exclude = {str(v).strip().lower() for v in rerolled}
    eligible = eligible_varieties(session, exclude=exclude)
    entry = random.Random(f"{year}-reroll-{len(rerolled)}").choice(eligible)
    return _pick_payload(entry, rerolled=rerolled)


def reroll(session: Session, year: Optional[int] = None,
           pinned: Optional[str] = None) -> dict:
    """Draw a new pick for the year. The replaced variety joins the rerolled
    list so it never comes back this year. ``pinned`` forces a specific
    curated variety (used by the chat confirm flow)."""
    year = year or date.today().year
    stored = _read_raw(session, year) or {}
    rerolled = list(stored.get("rerolled") or [])
    if stored.get("variety"):
        rerolled.append(stored["variety"])
    exclude = {str(v).strip().lower() for v in rerolled}
    # A pinned variety bypasses randomness but still honors exclusions.
    entry = None
    if pinned:
        want = pinned.strip().lower()
        entry = next((e for e in CHAOS_VARIETIES
                      if e["name"].strip().lower() == want), None)
        if entry and (entry["name"].strip().lower() in exclude
                      or _matches_history(entry, grown_names(session))
                      or entry["name"].strip().lower() in prior_chaos_picks(session)):
            entry = None
    if entry is None:
        preview = preview_reroll(session, year)
        entry = next(e for e in CHAOS_VARIETIES
                     if e["name"] == preview["variety"])
        rerolled = preview["rerolled"]
    payload = _pick_payload(entry, rerolled=rerolled)
    _write_raw(session, year, payload)
    return {"year": year, **payload}


def accept(session: Session, year: Optional[int] = None) -> dict:
    """Mark the year's pick accepted — and put it on the winter order list
    (a checked wishlist item, so the order assistant shows it)."""
    from app.models import WishlistItem

    year = year or date.today().year
    pick = current_pick(session, year)
    stored = _read_raw(session, year) or {}
    stored["accepted"] = True
    _write_raw(session, year, stored)
    # Surface on the order list: one checked wishlist item (no duplicates).
    variety = pick["variety"]
    exists = session.exec(select(WishlistItem)).all()
    if not any((w.variety_name or "").strip().lower() == variety.strip().lower()
               for w in exists):
        session.add(WishlistItem(
            variety_name=variety, vendor_name="",
            notes=f"🎲 {year} chaos pick — {pick.get('pitch', '')}",
            checked=True, date_added=date.today().isoformat()))
        session.commit()
    return {"year": year, **{**stored, "variety": variety}}
