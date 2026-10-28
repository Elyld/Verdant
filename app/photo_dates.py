"""Filename-derived photo dates + AI-generated-image detection.

Legacy albums (notably the reconstructed 2025 season) carry images whose
Immich asset has no date at all, so ``taken_at`` stays null and the album
has no chronology. The filenames usually carry the date instead:

- ``20250602_195615.jpg`` — direct ``YYYYMMDD_HHMMSS``
- ``file-<hash>-20250602_195615.jpg`` — same pattern, mid-name
- ``image-1761951517029.jpg`` / ``chatgpt-1759971053683.jpg`` — epoch ms

``parse_filename_date`` recovers those; anything else (including the
Immich placeholder names whose epoch is bogus) stays null rather than
getting an invented date. Epoch values are only trusted inside a sane
window (2010-01-01 .. tomorrow UTC) — a bogus in-window epoch cannot be
distinguished from a real one by name alone, and that limit is documented
rather than papered over.

``is_generated_filename`` flags AI-generated images by name (the observed
``chatgpt-*.jpg`` shape). It is a heuristic, not a provenance guarantee.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

# YYYYMMDD_HHMMSS anywhere in the basename (separator _ or -).
_DATETIME_RE = re.compile(r"(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})")
# A 13-digit epoch-milliseconds run, bounded by non-digits or string ends.
_EPOCH_MS_RE = re.compile(r"(?:^|[^0-9])(\d{13})(?:[^0-9]|$)")

_EPOCH_MIN = datetime(2010, 1, 1, tzinfo=timezone.utc)


def _basename(name: str) -> str:
    base = (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return base.split("?", 1)[0]


def parse_filename_date(name: str) -> datetime | None:
    """Best-effort date for a photo filename, naive UTC like the rest of
    Verdant's stored datetimes. Returns None when nothing parses."""
    base = _basename(name)
    if not base:
        return None
    m = _DATETIME_RE.search(base)
    if m:
        try:
            return datetime(*[int(g) for g in m.groups()])
        except ValueError:
            pass  # e.g. month 13: not a date, fall through to epoch
    m = _EPOCH_MS_RE.search(base)
    if m:
        try:
            dt = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        # Allow up to a day of clock skew into the future, nothing more.
        if _EPOCH_MIN <= dt <= now + timedelta(days=1):
            return dt.replace(tzinfo=None)
        return None
    return None


def is_generated_filename(name: str) -> bool:
    """True for the observed AI-generated filename shape (``chatgpt-*``)."""
    base = _basename(name).lower()
    return base.startswith("chatgpt-") or base.startswith("chatgpt_")
