"""Physical receipt scanning: photo -> structured invoice data via vision LLM.

Not every purchase comes through email, so the Costs page lets Josh photograph
a paper receipt. The image goes to the configured vision-capable chat model
(OpenRouter or Ollama, see app/llm.py) with a strict JSON prompt; nothing is
saved automatically — the UI shows the extraction for review and fills the
invoice form on confirmation.

Uses the same AI settings as the garden agent, so there's nothing new to
configure: if the key/model can already chat with photos, it can read receipts.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from app import llm as llm_mod

logger = logging.getLogger(__name__)

SCAN_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
SCAN_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

PROMPT = """Read this receipt photo and extract the purchase details.

Return ONLY a JSON object with exactly these keys:
{
  "vendor": string or null,        // store name as printed
  "order_date": "YYYY-MM-DD" or null,
  "order_number": string or null,  // receipt/order/transaction number if shown
  "total": number or null,         // the FINAL amount paid (not subtotal)
  "items_summary": string or null, // short comma-separated list of items
  "notes": string or null          // discounts, tender type, anything notable
}

Rules:
- Today is %s. Use it to resolve relative dates; never invent a date.
- "total" is the bottom-line amount the customer paid. If several amounts
  appear (subtotal, tax, savings), pick the grand total. If it's genuinely
  unclear, use null — never guess.
- Keep items_summary under 200 characters.
- Use null (not "") for anything not visible. Output JSON only, no markdown.
"""

# Keys the UI invoice form understands; anything else the model emits is dropped.
FIELDS = ("vendor", "order_number", "total", "items_summary", "notes", "order_date")


def extract_receipt(session, image_data_uri: str, today: date | None = None) -> dict:
    """Run the vision model over a receipt photo; return sanitized fields.

    Raises llm_mod.LLMError with a user-friendly message when AI is off,
    unconfigured, or the provider fails.
    """
    today = today or date.today()
    text = llm_mod.chat(
        session,
        [{"role": "user", "content": PROMPT % today.isoformat()}],
        json_mode=True,
        images=[image_data_uri],
    )
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("receipt scan: model did not return JSON: %r", text[:200])
        raise llm_mod.LLMError(
            "The AI didn't return readable receipt data — try a clearer photo."
        ) from exc
    if not isinstance(raw, dict):
        raise llm_mod.LLMError(
            "The AI didn't return readable receipt data — try a clearer photo."
        )
    return _sanitize(raw)


def _sanitize(raw: dict) -> dict:
    def _str(key: str, limit: int) -> str | None:
        v = raw.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s[:limit] or None

    def _total() -> float | None:
        v = raw.get("total")
        if v is None or isinstance(v, bool):
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return round(f, 2) if f >= 0 else None

    def _order_date() -> str | None:
        v = raw.get("order_date")
        if not isinstance(v, str):
            return None
        v = v.strip()[:10]
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError:
            return None

    return {
        "vendor": _str("vendor", 120),
        "order_number": _str("order_number", 80),
        "total": _total(),
        "items_summary": _str("items_summary", 500),
        "notes": _str("notes", 500),
        "order_date": _order_date(),
    }
