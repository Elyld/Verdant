"""Heuristic matching of invoice line items to seed packets.

Invoice ``items_summary`` text looks like::

    "Costoluto Fiorentino Tomato - ORGANIC SEED / 1/8 gram x1 $4.95; Fall Garlic Festival - GARLIC / three 8 oz pkgs x1 $46.95"

``suggest_packets`` parses that into item names and fuzzy-matches each one
against seed packet variety names. It's deliberately simple — the UI always
lets the user confirm or change the match.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Words that describe packaging / marketing rather than the variety.
_NOISE_WORDS = frozenset({
    "organic", "seed", "seeds", "plant", "plants", "live", "pack", "packs",
    "packet", "packets", "pkt", "each", "set", "sets", "sampler", "collection",
    "mix", "blend", "fresh", "heirloom", "hybrid", "open", "pollinated",
})

# Trailing " x2 $9.90" quantity/price tail on each item.
_QTY_PRICE_RE = re.compile(r"\s+x\d+(?:\.\d+)?\s*\$[\d.]+\s*$", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> frozenset:
    """Lowercased word tokens with punctuation stripped and noise removed."""
    return frozenset(
        w for w in _WORD_RE.findall(text.lower()) if w not in _NOISE_WORDS
    )


def parse_item_names(items_summary: str) -> List[str]:
    """Split an invoice items summary into per-item name strings.

    Splits on ";" and strips the trailing " xN $P.PP" quantity/price tail,
    leaving the human-readable product name (e.g. "Costoluto Fiorentino
    Tomato - ORGANIC SEED / 1/8 gram").
    """
    names = []
    for chunk in (items_summary or "").split(";"):
        name = _QTY_PRICE_RE.sub("", chunk).strip(" \t-–—")
        if name:
            names.append(name)
    return names


def _score(item_tokens: frozenset, packet_tokens: frozenset) -> float:
    """0..1 match score between an item's tokens and a packet variety's."""
    if not item_tokens or not packet_tokens:
        return 0.0
    if item_tokens == packet_tokens:
        return 1.0
    if packet_tokens <= item_tokens or item_tokens <= packet_tokens:
        return 0.9
    inter = len(item_tokens & packet_tokens)
    if not inter:
        return 0.0
    jaccard = inter / len(item_tokens | packet_tokens)
    # One shared token out of several is almost always noise for variety
    # names (e.g. "Cherokee Purple" vs "Pepper, Purple Beauty"); the subset
    # rule above already covers the genuinely good partial matches.
    return round(jaccard, 2) if jaccard >= 0.34 else 0.0


def best_packet_match(variety: str, packets: List[Any], threshold: float = 0.9):
    """Best-matching packet for a variety name, or ``(None, 0.0)``.

    Used when deriving packets from a receipt: a derived variety that already
    exists in the stash (a subset/superset token match, score >= threshold) is
    linked to the existing packet instead of creating a near-duplicate.
    """
    vtokens = _tokens(variety)
    best, best_score = None, 0.0
    for p in packets:
        score = _score(vtokens, _tokens(getattr(p, "variety_name", "")))
        if score > best_score:
            best, best_score = p, score
    if best_score >= threshold:
        return best, best_score
    return None, best_score


def suggest_packets(
    items_summary: str,
    packets: List[Any],
    per_item: int = 3,
    exclude_ids: frozenset = frozenset(),
) -> List[Dict[str, Any]]:
    """Rank seed packets against each parsed invoice item.

    ``packets`` are objects with ``id`` and ``variety_name`` (duck-typed so
    callers can pass ORM rows or plain dicts). Returns a flat ranked list of
    ``{packet_id, variety, matched_item, score}`` dicts, best score first,
    each packet appearing at most once.
    """
    packet_data = [
        (p.id, getattr(p, "variety_name", ""), _tokens(getattr(p, "variety_name", "")))
        for p in packets
        if p.id not in exclude_ids
    ]
    best: Dict[int, Dict[str, Any]] = {}
    for item in parse_item_names(items_summary):
        item_tokens = _tokens(item)
        ranked = sorted(
            (
                (score, pid, variety)
                for pid, variety, ptokens in packet_data
                if (score := _score(item_tokens, ptokens)) > 0
            ),
            reverse=True,
        )
        for score, pid, variety in ranked[:per_item]:
            if pid not in best or best[pid]["score"] < score:
                best[pid] = {
                    "packet_id": pid,
                    "variety": variety,
                    "matched_item": item,
                    "score": score,
                }
    return sorted(best.values(), key=lambda c: (-c["score"], c["variety"]))
