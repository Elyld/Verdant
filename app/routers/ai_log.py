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
    image: Optional[str] = None  # data:image/... URI or https:// URL; vision-capable models can see it


MAX_HISTORY = 8  # turns forwarded to the model; the client keeps the rest
MAX_IMAGE_LEN = 7_000_000  # ~5 MB base64 — an image bigger than this is rejected


def _chat_enabled(session: Session) -> bool:
    return (frost_mod.get_setting(session, "ai_chat_enabled") or "true") == "true"


_CHAT_SYSTEM = """You are Verdant, the friendly assistant inside a gardener's personal garden journal app. \
You answer questions about THEIR garden and help them log what they do. Be warm, concise, and practical — \
a knowledgeable gardening neighbor, never a lecture. Keep replies short (a few sentences) unless they ask for detail.

You have TOOLS — use them instead of guessing:
- Look things up with: plant_care_history, search_notes, seed_stash, planner_overview, reminders, \
season_advice, recall_notes, variety_performance, season_recap (photo season story), \
this_week_last_year, growth_check (photo growth check), frost_gamble, true_cost.
- When the gardener describes something they DID, or asks you to change something, call the matching \
write tool (log_watering, log_fertilization, log_harvest, log_observation, log_pest, add_seed_packet, \
update_plant, move_planting, record_autopsy). These create DRAFTS the gardener confirms before anything is saved — \
never claim you saved anything yourself.
- When the gardener asks to be reminded at a time or date, call set_reminder — it drafts a dated \
reminder they confirm. save_memory_note is only a note and can NEVER remind anyone; never promise \
a reminder without calling set_reminder.
- When the gardener says a plant died (or asks to mark one Done because it died), play coroner first: \
ask up to 3 quick questions — what did it look like at the end? sudden or gradual? weather or pests \
involved? — then call record_autopsy with the answers. Never log a death as a bare status change.

Each turn, respond with ONLY one JSON object:
- To use tools: {{"tool_calls": [{{"name": "<tool>", "args": {{...}}}}]}} (max 3 calls per turn)
- When done: {{"reply": "<your answer to the gardener>"}}
After tool calls you receive their results — then answer. If a tool errors, say what you couldn't find \
and ask for the missing detail instead of inventing it.

Rules:
- Use ONLY the garden context and tool results for facts about their plants, dates, and activity. \
Never invent plant names, varieties, dates, or numbers.
- Today is {today}. The gardener is in USDA zone {zone}.
- One draft per distinct thing the gardener did. For pure questions, no write tools.
- No markdown tables. Short paragraphs or a few bullets are fine.

Available tools:
{tools}

Garden context:
{context}"""


MAX_TOOL_ITERS = 3


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


_OR_MODELS_CACHE = {"at": 0.0, "models": []}
_OR_MODELS_TTL = 24 * 3600


@router.get("/openrouter-models")
def openrouter_models() -> dict:
    """All OpenRouter model ids with free ones flagged, cached 24h.
    Never raises — the Settings UI falls back to a text field on failure."""
    import time
    import urllib.request

    now = time.time()
    if _OR_MODELS_CACHE["models"] and now - _OR_MODELS_CACHE["at"] < _OR_MODELS_TTL:
        return {"models": _OR_MODELS_CACHE["models"]}
    models: list[dict] = []
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"User-Agent": "Verdant/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        for m in data.get("data", []):
            mid = m.get("id") or ""
            if not mid:
                continue
            pricing = m.get("pricing") or {}
            try:
                free = (mid.endswith(":free")
                        or (float(pricing.get("prompt") or 1) == 0
                            and float(pricing.get("completion") or 1) == 0))
            except (TypeError, ValueError):
                free = mid.endswith(":free")
            models.append({"id": mid, "name": m.get("name") or mid, "free": free})
        models.sort(key=lambda m: (not m["free"], m["name"].lower()))
        _OR_MODELS_CACHE.update(at=now, models=models)
    except Exception:
        pass
    return {"models": models}


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


def _draft_summary(d: dict) -> str:
    label = {"water": "watering", "fertilize": "feeding", "harvest": "harvest",
             "observe": "observation", "pest": "pest note", "note": "note",
             "seed": "seed packet", "plant_status": "status change",
             "plant_move": "container move",
             "reminder": "reminder"}.get(d.get("action"), d.get("action"))
    bits = [label]
    if d.get("plant_name"):
        bits.append(f"for {d['plant_name']}")
    if d.get("detail"):
        bits.append(f"({d['detail']})")
    return " ".join(bits)


def _chat_llm(session: Session, messages: list, images: list[str] | None = None) -> str:
    """One model call with the shared error contract."""
    try:
        return llm_mod.chat(session, messages, json_mode=True, timeout=120,
                            images=images)
    except llm_mod.LLMError as e:
        msg = str(e)
        if e.hint:
            msg += f" {e.hint}"
        raise HTTPException(502, msg)


@router.post("/chat")
def chat_endpoint(payload: ChatRequest, session: Session = Depends(get_session)) -> dict:
    """Chat with the garden assistant. Runs a small tool-calling loop:
    read tools execute immediately, write tools become drafts the user
    confirms in the UI. Returns {"reply", "drafts"}."""
    from app import ai_context as ai_context_mod
    from app import ai_tools as ai_tools_mod

    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(400, "Say something first.")
    if len(message) > 2000:
        raise HTTPException(400, "That's a lot — try a shorter message.")
    image = (payload.image or "").strip() or None
    if image:
        if not (image.startswith("data:image/") or image.startswith("https://")):
            raise HTTPException(
                400, "That image isn't usable — attach a photo as a data:image/... "
                     "URI or an https:// URL.")
        if len(image) > MAX_IMAGE_LEN:
            raise HTTPException(400, "That image is too large — keep it under ~5 MB.")
    if not _chat_enabled(session):
        raise HTTPException(400, "The chat assistant is off — enable it on the Settings page.")
    if not llm_mod.get_config(session)["enabled"]:
        raise HTTPException(400, "AI is off — enable it on the Settings page first.")

    context = ai_context_mod.build_context(session)
    today = Date.today()
    zone = frost_mod.get_setting(session, "zone") or "?"
    tools_json = json.dumps(ai_tools_mod.TOOLS)
    system = _CHAT_SYSTEM.format(
        today=today.strftime("%A, %B %d, %Y"), zone=zone,
        tools=tools_json, context=context)
    if image:
        system += ("\n\nThe gardener attached a photo with this message — you CAN see it. "
                   "Use what you see for pest ID, ripeness, or plant health, "
                   "and mention what you observe in your reply.")

    history = [
        {"role": m.role, "content": (m.content or "")[:1500]}
        for m in (payload.history or [])
        if m.role in ("user", "assistant") and (m.content or "").strip()
    ][-MAX_HISTORY:]
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": message}]
    images = [image] if image else None

    drafts: list[dict] = []
    reply: Optional[str] = None
    for turn in range(MAX_TOOL_ITERS):
        # The photo rides with the first call only — later turns send the
        # tool results, and re-sending the image would burn vision tokens
        # for no new information.
        content = _chat_llm(session, messages, images=images if turn == 0 else None)
        parsed = _extract_json_object(content)
        if parsed is None:
            reply = content.strip() or "…"
            break
        calls = parsed.get("tool_calls") or []
        if not calls:
            reply = str(parsed.get("reply") or "").strip() or "…"
            # Tolerate the old single-shot contract too.
            for raw in parsed.get("drafts") or []:
                d = _clean_draft(raw, _plant_names(session))
                if d:
                    drafts.append(d)
            break
        results = []
        for call in calls[:3]:
            name = (call or {}).get("name")
            args = (call or {}).get("args") or {}
            if name in ai_tools_mod.READ_TOOLS:
                results.append({"tool": name,
                                "result": ai_tools_mod.execute_read(session, name, args)})
            elif name in ai_tools_mod.WRITE_TOOL_ACTIONS:
                d = ai_tools_mod.build_write_draft(session, name, args)
                if d:
                    drafts.append(d)
                    results.append({"tool": name, "result":
                                    {"draft_created": _draft_summary(d)}})
                else:
                    results.append({"tool": name, "result":
                                    {"error": "couldn't build that draft — "
                                              "ask the gardener for the missing detail"}})
            else:
                results.append({"tool": name, "result":
                                {"error": f"unknown tool '{name}'"}})
        messages.append({"role": "assistant",
                         "content": json.dumps({"tool_calls": calls})})
        messages.append({"role": "user",
                         "content": "Tool results:\n" + json.dumps(results)})
    if reply is None:
        # The model kept calling tools; nudge it to answer now.
        messages.append({"role": "user", "content":
                         "No more tool calls — reply to the gardener now "
                         "with {\"reply\": \"...\"}."})
        content = _chat_llm(session, messages)
        parsed = _extract_json_object(content)
        reply = (str((parsed or {}).get("reply") or "").strip()
                 or content.strip() or "…")

    if drafts:
        stmt = select(Plant).where(Plant.status == "Growing")
        by_name = {p.variety_name.lower(): p.id for p in session.exec(stmt).all()}
        for d in drafts:
            if d["plant_name"] and not d["plant_id"]:
                d["plant_id"] = by_name.get(d["plant_name"].lower())
    return {"ok": True, "reply": reply, "drafts": drafts}


@router.get("/status")
def ai_status(session: Session = Depends(get_session)) -> dict:
    """Is the feature on, and is the provider reachable? Never raises."""
    return llm_mod.status(session)


def _interpret_text(session: Session, text: str) -> dict:
    """Core of /interpret: turn validated prose into draft log entries.

    Returns {"ok": True, "drafts": [...]} (plus a "message" when nothing was
    parseable). Drafts only — nothing is saved without user confirmation.
    """
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
    return _interpret_text(session, text)


class VoiceLogRequest(BaseModel):
    transcript: str


@router.post("/voice-log")
def voice_log(payload: VoiceLogRequest, session: Session = Depends(get_session)) -> dict:
    """AI-powered voice logging — the client does speech-to-text (Web Speech API)
    and POSTs the transcript; the server parses it into drafts through the same
    pipeline as /interpret. The existing client-side voice_log.js is the no-AI
    sibling; this is the AI sibling for a future mic button.

    Returns drafts only — nothing is saved without user confirmation.
    """
    transcript = (payload.transcript or "").strip()
    if not transcript:
        raise HTTPException(400, "Tell me what you did first.")
    if len(transcript) > 2000:
        raise HTTPException(400, "That's a lot — try one or two sentences.")
    if not llm_mod.get_config(session)["enabled"]:
        raise HTTPException(400, "AI is off — enable it on the Settings page first.")
    return _interpret_text(session, transcript)


class SeasonRecapRequest(BaseModel):
    plant_id: Optional[int] = None
    plant: Optional[str] = ""


@router.post("/season-recap")
def season_recap_endpoint(payload: SeasonRecapRequest,
                          session: Session = Depends(get_session)) -> dict:
    """Narrate one plant's season from its photos (read-only).

    Gathers the plant's photos across the season (Immich album matches +
    observation photos) and asks the configured vision-capable chat model to
    tell the story. Photos only ever go to the gardener's already-configured
    LLM provider — the same one the chat's photo-vision feature uses.
    """
    import app.ai_tools as ai_tools_mod
    import app.season_recap as recap_mod

    plant = session.get(Plant, payload.plant_id) if payload.plant_id else None
    if plant is None:
        plant = ai_tools_mod._match_plant(session, payload.plant or "")
    if plant is None:
        raise HTTPException(404, "Plant not found — name a plant from the Plants page.")
    if not llm_mod.get_config(session)["enabled"]:
        raise HTTPException(400, "AI is off — enable it on the Settings page first.")
    return recap_mod.build_recap(session, plant)
