"""Derive seed-packet candidates from an invoice's line items.

An invoice's ``items_summary`` is a ``";"``-separated list of
``name xN $P.PP`` chunks (see ``app.packet_match``). This module turns those
chunks into SeedPacket-shaped dicts so a receipt can grow the seed stash
automatically instead of the user re-typing every variety.

Deliberately conservative: anything that looks like a container, tool, or
growing supply is dropped (``is_seed_item``), the variety name is normalized
against the vendor formats we actually see, and the category comes from a
keyword table with a vendor hint fallback. The API surfaces the result as a
preview the user confirms before anything is written.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Trailing " x2 $9.90" quantity/price on an item chunk (not end-anchored: some
# vendors append "(Listed member: ...)" after it).
_QTY_PRICE_RE = re.compile(r"\s+x(\d+(?:\.\d+)?)\s*\$\s*([\d.]+)\b", re.IGNORECASE)

# Category keyword table, checked in order; first hit wins. Matched on word
# boundaries (with a plural "s"), so "pea" never fires inside "Peach".
_CATEGORY_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Ground Cherry", ("ground cherry",)),
    ("Pepper", (
        "pepper", "habanero", "cayenne", "scotch bonnet", "scotch", "fatalii",
        "aji", "jalapeno", "jalapeño", "ghost", "reaper", "thunderbolt",
        "chili", "chile", "paprika", "serrano", "poblano", "anaheim",
    )),
    ("Tomato", ("tomato",)),
    ("Eggplant", ("eggplant", "aubergine")),
    ("Sunflower", ("sunflower",)),
    ("Summer Squash", (
        "squash", "zucchini", "scallop", "patty pan", "crookneck", "delicata",
    )),
    ("Garlic", ("garlic",)),
    ("Onion", ("onion", "shallot", "leek")),
    ("Pea", ("pea", "sugar snap")),
    ("Garden Bean", ("bean",)),
    ("Tobacco", ("tobacco",)),
    ("Lettuce", (
        "lettuce", "salad", "greens", "arugula", "spinach", "chard", "kale",
        "mizuna",
    )),
    ("Herb", (
        "basil", "chives", "cumin", "parsley", "dill", "mint", "sage",
        "oregano", "thyme", "rosemary", "cilantro", "stevia", "mugwort",
        "skullcap", "marshmallow", "wintergreen", "toothache", "lavender",
        "chamomile", "fennel", "borage", "calendula", "nettle", "yarrow",
        "herb",
    )),
    ("Flower", (
        "alyssum", "lantern", "bunny tails", "marigold", "zinnia", "cosmos",
        "poppy", "nasturtium", "wildflower", "iris", "dahlia", "tulip",
        "daffodil", "lupine", "columbine", "snapdragon", "petunia", "flower",
    )),
    ("Gourd", ("gourd", "luffa", "loofah")),
    ("Melon", ("melon", "watermelon", "cantaloupe", "muskmelon")),
    ("Cucumber", ("cucumber",)),
    ("Carrot", ("carrot",)),
    ("Radish", ("radish",)),
    ("Beet", ("beet",)),
    ("Broccoli", ("broccoli",)),
    ("Cauliflower", ("cauliflower",)),
    ("Cabbage", ("cabbage",)),
    ("Corn", ("corn", "maize")),
)

# Fallback category when the item name gives no signal — keyed off the vendor.
_VENDOR_CATEGORY_HINTS = (
    ("pepper", "Pepper"),
    ("tomat", "Tomato"),
)

# Anything matching these is a container / supply / tool, not a seed to stash.
_NON_SEED_KEYWORDS = (
    "grow bag", "fabric pot", "aeration", "planter", "pot ", "pots",
    "tray", "dome", "soil", "fertiliz", "nutrient", "compost",
    "trellis", "netting", "stake", "cage", "hose", "w/ handles", "w/handles",
    "flap door", "cloche", "mulch", "watering", "shears", "gloves", "trowel",
    "seed starting", "seedling", "label", "marker", "propagat", "germinat",
    "heat mat", "grow light", "lamp", "row cover",
)

# " - SEED / 3 grams", " - ORGANIC SEED / 1/8 gram", " - GARLIC / 8 ounces".
_PACK_TAIL_RE = re.compile(
    r"\s*[-–—]\s*(?:organic\s+)?"
    r"(?:seeds?|plants?|garlic|bulbs?|tubers?|rhizomes?|crowns?|corms?)"
    r"\b\s*/.*$",
    re.IGNORECASE,
)
# "– 50 Seeds", "- 15 Varieties", " 100 seeds" at the end.
_TRAILING_COUNT_RE = re.compile(
    r"\s*[-–—]?\s*\d+\s*(?:seeds?|plants?|varieties|grams?|g\b|oz|packets?|count)\b.*$",
    re.IGNORECASE,
)
# A discount note "(50% off - regular price $3.35)".
_DISCOUNT_RE = re.compile(r"\s*\((?:[^()]*\b(?:off|price|sale|discount)\b[^()]*)\)", re.IGNORECASE)
# A trailing qualifier "(organic)" / "(treated)" we don't want on the variety.
_QUALIFIER_RE = re.compile(
    r"\s*\((?:organic|conventional|treated|untreated|heirloom|hybrid|f1|open[-\s]?pollinated)\)\s*$",
    re.IGNORECASE,
)
# A trailing parenthetical with a colon — vendor bookkeeping, e.g.
# "(Listed member: small seed)".
_META_PAREN_RE = re.compile(r"\s*\([^()]*:[^()]*\)\s*$")
# Seed-Savers style "Category, Variety".
_COMMA_CATEGORY_RE = re.compile(r"^([^,]{2,24}?)\s*,\s*(.+)$")
# Possessive after title-casing: "Kellogg'S" -> "Kellogg's".
_POSSESSIVE_RE = re.compile(r"(?<=\w)'S\b")


def _has_keyword(text: str, keyword: str) -> bool:
    """Word-boundary match allowing a plural \"s\" (pea != peach, pepper = peppers)."""
    return re.search(
        r"(?<![a-z])" + re.escape(keyword.lower()) + r"s?(?![a-z])", text.lower()
    ) is not None


def _detect_category(text: str) -> str:
    """First category whose keyword appears in ``text`` (case-insensitive)."""
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(_has_keyword(text, k) for k in keywords):
            return category
    return ""


def _pack_size(name: str) -> str:
    """The trailing pack-size text, e.g. "3 grams" / "25 seeds", else ""."""
    m = re.search(
        r"[-–—]\s*(?:organic\s+)?(?:seeds?|plants?|garlic|bulbs?)\b\s*/\s*(.+?)\s*$",
        name, re.IGNORECASE,
    )
    if not m:
        return ""
    size = _DISCOUNT_RE.sub("", m.group(1)).strip()
    size = re.sub(r"\s*\(.*$", "", size).strip()
    return size


def is_seed_item(name: str) -> bool:
    """False for containers / supplies / tools that shouldn't become packets."""
    low = (name or "").lower()
    if not low.strip():
        return False
    return not any(k in low for k in _NON_SEED_KEYWORDS)


def _title(text: str) -> str:
    text = text.title() if text.isupper() else text
    return _POSSESSIVE_RE.sub("'s", text)


def _clean_variety(name: str, category: str, from_comma: bool) -> str:
    """Reduce an item name to the variety name (no packaging, no category)."""
    text = name.strip()
    text = _DISCOUNT_RE.sub("", text)
    text = _META_PAREN_RE.sub("", text)
    # Cut the " - SEED / size" and "– 50 Seeds" tails.
    text = _PACK_TAIL_RE.sub("", text)
    text = _TRAILING_COUNT_RE.sub("", text)
    # Drop a stranded category word at the head (e.g. "Tobacco Seeds - KY 15").
    if category and not from_comma:
        head = re.compile(
            rf"^{re.escape(category)}\b\s*(?:seeds?|plants?)?\s*[-–—,:]?\s*",
            re.IGNORECASE,
        )
        text = head.sub("", text)
    text = _QUALIFIER_RE.sub("", text)
    text = re.sub(r"\s*[-–—/:,]\s*$", "", text).strip(" ,-–—")
    text = re.sub(r"\s{2,}", " ", text).strip()
    if not text:
        return name.strip()
    return _title(text)


def derive_packet(name: str, vendor: str = "", qty: float = 1,
                  year: Optional[int] = None) -> Dict[str, object]:
    """Turn one line-item name into a SeedPacket-shaped dict."""
    working = _DISCOUNT_RE.sub("", name).strip()
    from_comma = False
    category = ""
    # "Category, Variety" (Seed Savers) — the head is the vendor's own label.
    m = _COMMA_CATEGORY_RE.match(working)
    if m and _detect_category(m.group(1)):
        category = _detect_category(m.group(1))
        working = m.group(2).strip()
        from_comma = True
    if not category:
        category = _detect_category(working)
    if not category:
        low_vendor = (vendor or "").lower()
        for needle, cat in _VENDOR_CATEGORY_HINTS:
            if needle in low_vendor and cat:
                category = cat
                break
    variety = _clean_variety(working, category, from_comma)
    size = _pack_size(name)
    quantity = size or (f"x{int(qty)}" if qty and qty != 1 else "1 packet")
    return {
        "variety_name": variety,
        "category": category,
        "species_type": "",
        "quantity": quantity,
        "vendor_name": vendor,
        "year_acquired": year,
    }


def parse_line_items(items_summary: str) -> List[Dict[str, object]]:
    """Split ``items_summary`` into ``{name, qty, price, is_seed}`` dicts."""
    out: List[Dict[str, object]] = []
    for chunk in (items_summary or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        qty, price = 1.0, None
        m = _QTY_PRICE_RE.search(chunk)
        if m:
            qty = float(m.group(1))
            price = float(m.group(2))
            chunk = (chunk[: m.start()] + chunk[m.end():]).strip()
        name = _DISCOUNT_RE.sub("", chunk).strip(" \t-–—")
        if not name:
            continue
        out.append({
            "name": name,
            "qty": qty,
            "price": price,
            "is_seed": is_seed_item(name),
        })
    return out


def candidates_from_invoice(items_summary: str, vendor: str = "",
                            order_date: str = "") -> List[Dict[str, object]]:
    """Seed-packet candidates (de-duped within the invoice) for an invoice."""
    year: Optional[int] = None
    if order_date:
        m = re.match(r"(\d{4})", str(order_date))
        if m:
            year = int(m.group(1))
    seen = set()
    candidates: List[Dict[str, object]] = []
    for item in parse_line_items(items_summary):
        if not item["is_seed"]:
            continue
        packet = derive_packet(item["name"], vendor, item["qty"], year)
        key = (str(packet["variety_name"]).lower(), (vendor or "").lower())
        if not packet["variety_name"] or key in seen:
            continue
        seen.add(key)
        packet["source_item"] = item["name"]
        packet["unit_price"] = item["price"]
        candidates.append(packet)
    return candidates
