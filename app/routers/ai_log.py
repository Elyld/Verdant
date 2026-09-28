"""Local-model "tell it what you did" for Quick Log.

Opt-in (Settings → Local AI, default OFF). POSTs the user's sentence to an
Ollama-compatible server on their own machine and turns the reply into *draft*
log entries — nothing is ever written without the user confirming each draft
in the UI. All failures degrade to a friendly message; the endpoint never
raises a stack trace at the caller.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import frost as frost_mod
from app.database import get_session
from app.models import Plant

router = APIRouter(prefix="/api/ai", tags=["ai"])

ACTIONS = ("water", "fertilize", "observe", "harvest", "pest", "note")
DEFAULT_BASE = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:4b"


def _config(session: Session) -> dict:
    return {
        "enabled": (frost_mod.get_setting(session, "local_ai_enabled") or "false") == "true",
        "base_url": (frost_mod.get_setting(session, "local_ai_base_url") or DEFAULT_BASE).strip().rstrip("/"),
        "model": (frost_mod.get_setting(session, "local_ai_model") or DEFAULT_MODEL).strip(),
    }


def _plant_names(session: Session, limit: int = 40) -> list[str]:
    stmt = select(Plant.variety_name).where(Plant.status == "Growing").limit(limit)
    return [n for n in session.exec(stmt).all() if n]


def _post_json(url: str, payload: dict, timeout: int) -> dict:
    """POST JSON, return the decoded body. Raises on any failure."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "verdant-garden-log"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_prompt(text: str, plants: list[str]) -> str:
    plant_list = ", ".join(plants) if plants else "(no growing plants recorded)"
    return (
        "You are a garden log parser. The user describes what they did in their garden. "
        "Respond with ONLY a JSON array, no other text, no markdown fences.\n"
        'Each item: {"action": "<one of: water, fertilize, observe, harvest, pest, note>", '
        '"plant": "<exact plant name from the list, or null>", '
        '"amount": <number or null>, "unit": "<unit like oz, or null>", '
        '"detail": "<for fertilize: the product used; for pest: the pest name; else null>", '
        '"notes": "<short note>"}\n'
        f"The gardener's growing plants: {plant_list}\n"
        "Rules: one item per distinct thing they did. "
        "If they name a plant not in the list, use plant=null and put the name in notes. "
        "amount is a harvest count, or a feed/water quantity with its unit; otherwise null. "
        "Keep notes under 20 words.\n"
        f'User said: "{text}"'
    )


def _extract_json_array(raw: str) -> Optional[list]:
    """Pull a JSON array out of model output (strips code fences). None if unparseable."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, list) else None


def _clean_draft(item: dict, plants: list[str]) -> Optional[dict]:
    """Validate one model-produced draft; None when it's junk."""
    if not isinstance(item, dict):
        return None
    action = item.get("action")
    if action not in ACTIONS:
        return None
    plant_name = item.get("plant")
    plant_id = None
    if plant_name:
        match = next((p for p in plants if p.lower() == str(plant_name).lower()), None)
        if match is None:
            plant_name = None  # unknown plant → notes carry it
        else:
            plant_name = match
    amount = item.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    unit = item.get("unit")
    unit = str(unit)[:12] if unit else None
    detail = item.get("detail")
    detail = str(detail)[:120] if detail else None
    notes = str(item.get("notes") or "")[:500]
    return {
        "action": action,
        "plant_id": plant_id,  # resolved client-side from plant_name
        "plant_name": plant_name,
        "amount": amount,
        "unit": unit,
        "detail": detail,
        "notes": notes,
    }


class InterpretRequest(BaseModel):
    text: str


@router.get("/status")
def ai_status(session: Session = Depends(get_session)) -> dict:
    """Is the feature on, and is the model server reachable? Never raises."""
    cfg = _config(session)
    if not cfg["enabled"]:
        return {"enabled": False, "reachable": False, "model": cfg["model"]}
    try:
        body = _post_json(f"{cfg['base_url']}/api/tags", {}, timeout=5)
        models = [m.get("name") for m in (body.get("models") or []) if isinstance(m, dict)]
        return {"enabled": True, "reachable": True, "model": cfg["model"], "models": models}
    except Exception:
        return {"enabled": True, "reachable": False, "model": cfg["model"],
                "hint": f"Could not reach {cfg['base_url']} — is the model server running?"}


@router.post("/interpret")
def interpret(payload: InterpretRequest, session: Session = Depends(get_session)) -> dict:
    """Turn a sentence into draft log entries. Returns drafts only — the
    caller writes them through the normal endpoints after user confirmation.
    """
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "Tell me what you did first.")
    if len(text) > 2000:
        raise HTTPException(400, "That's a lot — try one or two sentences.")
    cfg = _config(session)
    if not cfg["enabled"]:
        raise HTTPException(400, "Local AI is off — enable it on the Settings page first.")
    plants = _plant_names(session)
    prompt = _build_prompt(text, plants)
    try:
        body = _post_json(
            f"{cfg['base_url']}/api/chat",
            {"model": cfg["model"], "stream": False, "format": "json",
             "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        content = ((body.get("message") or {}).get("content")) or ""
    except Exception:
        raise HTTPException(
            502,
            f"Couldn't reach the model at {cfg['base_url']}. "
            "Is it running, and is the base URL right?",
        )
    items = _extract_json_array(content)
    if items is None:
        return {"ok": True, "drafts": [],
                "message": "Couldn't make sense of that — try shorter sentences, one thing at a time."}
    drafts = [d for d in (_clean_draft(i, plants) for i in items) if d]
    # resolve plant names → ids for the confirm step
    if drafts:
        stmt = select(Plant).where(Plant.status == "Growing")
        by_name = {p.variety_name.lower(): p.id for p in session.exec(stmt).all()}
        for d in drafts:
            if d["plant_name"]:
                d["plant_id"] = by_name.get(d["plant_name"].lower())
    if not drafts:
        return {"ok": True, "drafts": [],
                "message": "Nothing loggable in there — try e.g. 'watered the tomatoes and harvested 3 peppers'."}
    return {"ok": True, "drafts": drafts}
