"""Turn "I watered the tomatoes" into draft log entries.

Opt-in (Settings → AI, default OFF). POSTs the user's sentence to the
configured AI provider (Ollama on the user's own machine, or OpenRouter's
cloud API) and turns the reply into *draft* log entries — nothing is ever
written without the user confirming each draft in the UI. All failures
degrade to a friendly message; the endpoint never raises a stack trace
at the caller.
"""
from __future__ import annotations

import json
from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import frost as frost_mod
from app import llm as llm_mod
from app.database import get_session
from app.models import Plant

router = APIRouter(prefix="/api/ai", tags=["ai"])

ACTIONS = ("water", "fertilize", "observe", "harvest", "pest", "note")


def _plant_names(session: Session, limit: int = 40) -> list[str]:
    stmt = select(Plant.variety_name).where(Plant.status == "Growing").limit(limit)
    return [n for n in session.exec(stmt).all() if n]


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
    except ValueError:
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


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str = ""


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


MAX_HISTORY = 8  # turns forwarded to the model; the client keeps the rest


def _chat_enabled(session: Session) -> bool:
    return (frost_mod.get_setting(session, "ai_chat_enabled") or "true") == "true"


_CHAT_SYSTEM = """You are Verdant, the friendly assistant inside a gardener's personal garden journal app. \
You answer questions about THEIR garden and help them log what they do. Be warm, concise, and practical — \
a knowledgeable gardening neighbor, never a lecture. Keep replies short (a few sentences) unless they ask for detail.

Rules:
- Use ONLY the garden context below for facts about their plants, dates, and activity. Never invent plant names, varieties, dates, or numbers. If the context doesn't say, say you don't see it recorded.
- Today is {today}. The gardener is in USDA zone {zone}.
- When they describe something they DID (watered, fed, harvested, saw pests, noticed something), put structured drafts in "drafts" AND mention them briefly in "reply". Drafts use: {{"action": "<water|fertilize|observe|harvest|pest|note>", "plant": "<exact plant name from context, or null>", "amount": <number or null>, "unit": "<unit or null>", "detail": "<product for fertilize, pest name for pest, else null>", "notes": "<short note>"}}. One draft per distinct thing. Unknown plant → plant=null, name in notes.
- For pure questions (advice, "when did I last…", planning), "drafts" is [].
- Never claim to have saved anything — the gardener confirms every draft before it's written.
- No markdown tables. Short paragraphs or a few bullets are fine.

Respond with ONLY a JSON object: {{"reply": "<your answer>", "drafts": [<drafts or empty>]}}.

Garden context:
{context}"""


def _extract_json_object(raw: str) -> Optional[dict]:
    """Pull a JSON object out of model output. None if unparseable."""
    import json as json_mod

    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json_mod.loads(text[start:end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


@router.get("/chat-status")
def chat_status(session: Session = Depends(get_session)) -> dict:
    """Should the floating chat assistant show? Combines the chat toggle
    with the provider's own status. Never raises."""
    st = llm_mod.status(session)
    enabled = _chat_enabled(session) and bool(st.get("enabled"))
    out = {"enabled": enabled, "provider": st.get("provider"),
           "reachable": bool(st.get("reachable"))}
    if enabled and not out["reachable"]:
        out["hint"] = st.get("hint") or "The AI provider isn't reachable — check Settings → AI."
    return out


@router.post("/chat")
def chat_endpoint(payload: ChatRequest, session: Session = Depends(get_session)) -> dict:
    """Chat with the garden assistant. Returns {"reply", "drafts"} — drafts
    are only ever written after the user confirms them in the UI."""
    from app import ai_context as ai_context_mod

    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(400, "Say something first.")
    if len(message) > 2000:
        raise HTTPException(400, "That's a lot — try a shorter message.")
    if not _chat_enabled(session):
        raise HTTPException(400, "The chat assistant is off — enable it on the Settings page.")
    if not llm_mod.get_config(session)["enabled"]:
        raise HTTPException(400, "AI is off — enable it on the Settings page first.")

    context = ai_context_mod.build_context(session)
    today = Date.today()
    zone = frost_mod.get_setting(session, "zone") or "?"
    system = _CHAT_SYSTEM.format(
        today=today.strftime("%A, %B %d, %Y"), zone=zone, context=context)

    history = [
        {"role": m.role, "content": (m.content or "")[:1500]}
        for m in (payload.history or [])
        if m.role in ("user", "assistant") and (m.content or "").strip()
    ][-MAX_HISTORY:]
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": message}]
    try:
        content = llm_mod.chat(session, messages, json_mode=True, timeout=120)
    except llm_mod.LLMError as e:
        msg = str(e)
        if e.hint:
            msg += f" {e.hint}"
        raise HTTPException(502, msg)

    parsed = _extract_json_object(content)
    if parsed is None:
        # Model didn't follow the JSON contract — show the raw text, no drafts.
        return {"ok": True, "reply": content.strip() or "…", "drafts": []}
    reply = str(parsed.get("reply") or "").strip() or "…"

    plants = _plant_names(session)
    raw_drafts = parsed.get("drafts") or []
    drafts = [d for d in (_clean_draft(i, plants) for i in raw_drafts) if d]
    if drafts:
        stmt = select(Plant).where(Plant.status == "Growing")
        by_name = {p.variety_name.lower(): p.id for p in session.exec(stmt).all()}
        for d in drafts:
            if d["plant_name"]:
                d["plant_id"] = by_name.get(d["plant_name"].lower())
    return {"ok": True, "reply": reply, "drafts": drafts}


@router.get("/status")
def ai_status(session: Session = Depends(get_session)) -> dict:
    """Is the feature on, and is the provider reachable? Never raises."""
    return llm_mod.status(session)


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
    if not llm_mod.get_config(session)["enabled"]:
        raise HTTPException(400, "AI is off — enable it on the Settings page first.")
    plants = _plant_names(session)
    prompt = _build_prompt(text, plants)
    try:
        content = llm_mod.chat(
            session, [{"role": "user", "content": prompt}], json_mode=True
        )
    except llm_mod.LLMError as e:
        msg = str(e)
        if e.hint:
            msg += f" {e.hint}"
        raise HTTPException(502, msg)
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
