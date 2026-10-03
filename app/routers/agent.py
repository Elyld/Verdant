"""Persistent agent self — the chat assistant's memory, threads, and drafts.

The assistant is no longer a stateless chatbot:

- ``agent_files`` — three text files it reads into its prompt every turn:
  ``persona`` (who it is), ``operating_notes`` (lessons learned),
  ``memory`` (durable facts). ``GET/PUT /api/agent/files``.
- ``agent_conversations`` / ``agent_messages`` — full chat threads, so a
  browser refresh never loses the conversation.
- ``agent_drafts`` — every confirm-before-save draft (garden logs AND
  memory-write proposals) persisted server-side until confirmed/discarded.

Nothing here writes silently: drafts are applied only through
``POST /drafts/{id}/confirm``, one at a time, after the gardener's OK.
"""
from __future__ import annotations

import json
from datetime import date as Date
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import llm as llm_mod
from app.database import get_session
from app.models import (
    AGENT_FILES,
    AgentConversation,
    AgentDraft,
    AgentFile,
    AgentMessage,
    Container,
    FertilizationLog,
    Harvest,
    ObservationLog,
    PestLog,
    Plant,
    Planting,
    SeedPacket,
    UserReminder,
    WateringLog,
)
from app.routers.ai_log import _chat_enabled, run_agent_turn

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _require_chat(session: Session) -> None:
    if not _chat_enabled(session):
        raise HTTPException(400, "The chat assistant is off — enable it on the Settings page.")
    if not llm_mod.get_config(session)["enabled"]:
        raise HTTPException(400, "AI is off — enable it on the Settings page first.")


# --------------------------------------------------------------------------- #
# Identity files
# --------------------------------------------------------------------------- #

def _file_row(session: Session, name: str) -> AgentFile:
    from app import database as database_mod

    database_mod._seed_agent_files()  # never clobbers existing content
    row = session.get(AgentFile, name)
    if row is None:  # defensive — seeding runs on every read path
        raise HTTPException(404, f"Unknown agent file '{name}'.")
    return row


@router.get("/files")
def list_files(session: Session = Depends(get_session)) -> dict:
    """All three identity files: persona, operating_notes, memory."""
    return {"files": [
        {"name": f.name, "content": f.content or "",
         "updated_at": f.updated_at.isoformat() if f.updated_at else None}
        for f in (_file_row(session, n) for n in AGENT_FILES)
    ]}


class FileUpdate(BaseModel):
    content: str = ""


@router.put("/files/{name}")
def update_file(name: str, payload: FileUpdate,
                session: Session = Depends(get_session)) -> dict:
    """Direct-edit one identity file from the UI. The agent itself can only
    propose changes via the propose_memory_write tool (confirm-before-save)."""
    if name not in AGENT_FILES:
        raise HTTPException(404, f"Unknown agent file '{name}'.")
    row = _file_row(session, name)
    row.content = (payload.content or "")[:20000]
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    return {"ok": True, "name": name}


# --------------------------------------------------------------------------- #
# Conversations
# --------------------------------------------------------------------------- #

def _conv_or_404(session: Session, conv_id: int) -> AgentConversation:
    conv = session.get(AgentConversation, conv_id)
    if conv is None:
        raise HTTPException(404, f"Conversation {conv_id} not found.")
    return conv


def _draft_public(d: AgentDraft) -> dict:
    try:
        payload = json.loads(d.payload_json or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {"id": d.id, "conversation_id": d.conversation_id,
            "kind": d.kind, "payload": payload,
            "created_at": d.created_at.isoformat() if d.created_at else None}


@router.get("/conversations")
def list_conversations(session: Session = Depends(get_session)) -> dict:
    """Threads, newest first, with message + pending-draft counts."""
    convs = session.exec(select(AgentConversation)
                         .order_by(AgentConversation.updated_at.desc())).all()
    out = []
    for c in convs:
        msg_count = len(session.exec(
            select(AgentMessage.id)
            .where(AgentMessage.conversation_id == c.id)).all())
        draft_count = len(session.exec(
            select(AgentDraft.id)
            .where(AgentDraft.conversation_id == c.id)).all())
        out.append({"id": c.id, "title": c.title,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                    "message_count": msg_count, "draft_count": draft_count})
    return {"conversations": out}


class ConversationCreate(BaseModel):
    title: str = ""


@router.post("/conversations", status_code=201)
def create_conversation(payload: ConversationCreate,
                        session: Session = Depends(get_session)) -> dict:
    title = (payload.title or "").strip()[:120] or "New chat"
    conv = AgentConversation(title=title)
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return {"ok": True, "id": conv.id, "title": conv.title}


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int,
                        session: Session = Depends(get_session)) -> dict:
    conv = _conv_or_404(session, conv_id)
    for m in session.exec(select(AgentMessage)
                          .where(AgentMessage.conversation_id == conv.id)).all():
        session.delete(m)
    for d in session.exec(select(AgentDraft)
                          .where(AgentDraft.conversation_id == conv.id)).all():
        session.delete(d)
    session.delete(conv)
    session.commit()
    return {"ok": True}


@router.get("/conversations/{conv_id}/messages")
def list_messages(conv_id: int,
                  session: Session = Depends(get_session)) -> dict:
    _conv_or_404(session, conv_id)
    rows = session.exec(select(AgentMessage)
                        .where(AgentMessage.conversation_id == conv_id)
                        .order_by(AgentMessage.id)).all()
    return {"messages": [
        {"id": m.id, "role": m.role, "content": m.content,
         "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in rows]}


class ChatTurn(BaseModel):
    message: str
    image: Optional[str] = None  # data:image/... URI or https:// URL


@router.post("/conversations/{conv_id}/messages")
def chat_turn(conv_id: int, payload: ChatTurn,
              session: Session = Depends(get_session)) -> dict:
    """One assistant turn inside a thread.

    The user message is saved, history + the agent's identity files load
    into the prompt, the tool loop runs, and both the reply and every
    draft are persisted — a refresh loses nothing.
    """
    _require_chat(session)
    conv = _conv_or_404(session, conv_id)
    text = (payload.message or "").strip()
    if not text:
        raise HTTPException(400, "Say something first.")
    if len(text) > 2000:
        raise HTTPException(400, "That's a lot — try a shorter message.")
    image = (payload.image or "").strip() or None
    if image and not (image.startswith("data:image/") or image.startswith("https://")):
        raise HTTPException(400, "That image isn't usable.")

    session.add(AgentMessage(conversation_id=conv.id, role="user", content=text))

    past = session.exec(select(AgentMessage)
                        .where(AgentMessage.conversation_id == conv.id)
                        .order_by(AgentMessage.id.desc()).limit(20)).all()
    history = [{"role": m.role, "content": m.content}
               for m in reversed(past) if m.role in ("user", "assistant")][-10:]

    result = run_agent_turn(session, text, history, image=image)

    assistant_row = AgentMessage(conversation_id=conv.id, role="assistant",
                                 content=result["reply"] or "…")
    session.add(assistant_row)
    session.flush()  # id for the response, not strictly needed

    drafts_out = []
    for d in result["drafts"]:
        kind = str(d.get("action") or "note")
        row = AgentDraft(conversation_id=conv.id, kind=kind,
                         payload_json=json.dumps(d))
        session.add(row)
        session.flush()
        drafts_out.append(_draft_public(row))

    if conv.title == "New chat":
        conv.title = (text[:60] + "…") if len(text) > 60 else text
    conv.updated_at = datetime.now()
    session.add(conv)
    session.commit()

    return {"ok": True, "reply": result["reply"], "drafts": drafts_out,
            "assistant_message_id": assistant_row.id}


# --------------------------------------------------------------------------- #
# Drafts — confirm-before-save, persisted server-side
# --------------------------------------------------------------------------- #

@router.get("/drafts")
def list_drafts(conversation_id: Optional[int] = None,
                session: Session = Depends(get_session)) -> dict:
    stmt = select(AgentDraft).order_by(AgentDraft.id)
    if conversation_id is not None:
        stmt = stmt.where(AgentDraft.conversation_id == conversation_id)
    return {"drafts": [_draft_public(d) for d in session.exec(stmt).all()]}


def _draft_or_404(session: Session, draft_id: int) -> AgentDraft:
    d = session.get(AgentDraft, draft_id)
    if d is None:
        raise HTTPException(404, f"Draft {draft_id} not found.")
    return d


class DraftApplyError(Exception):
    """A draft that can't be applied yet — the message goes to the gardener."""


def _need_plant(session: Session, payload: dict) -> Plant:
    pid = payload.get("plant_id")
    plant = session.get(Plant, pid) if pid else None
    if plant is None:
        name = (payload.get("plant_name") or "").strip().lower()
        if name:
            plant = session.exec(select(Plant)
                                 .where(Plant.status == "Growing")).all()
            plant = next((p for p in plant
                          if (p.variety_name or "").lower() == name), None)
    if plant is None:
        raise DraftApplyError("Pick a plant for this draft first.")
    return plant


def apply_draft(session: Session, draft: AgentDraft) -> str:
    """Apply one confirmed draft. Returns a short human summary.

    Mirrors the old in-chat confirm flow: one draft, one save, nothing
    extra. Raises DraftApplyError when the draft needs more info.
    """
    try:
        payload = json.loads(draft.payload_json or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        raise DraftApplyError("That draft was unreadable — discard it and ask again.")
    kind = draft.kind or payload.get("action") or "note"
    today = Date.today().isoformat()

    if kind == "water":
        plant = _need_plant(session, payload)
        location_id = plant.location_id
        if location_id is None:
            raise DraftApplyError(
                f"Watering {plant.variety_name} needs a location — "
                "set one on the plant first.")
        session.add(WateringLog(location_id=location_id, plant_id=plant.id,
                                date=today, notes=payload.get("notes") or None))
        return f"Watered {plant.variety_name}."

    if kind == "fertilize":
        plant = _need_plant(session, payload)
        product = (payload.get("detail") or "").strip()
        if not product:
            raise DraftApplyError("Feeding needs a product name.")
        amount = payload.get("amount")
        unit = payload.get("unit")
        amount_used = " ".join(str(x) for x in (amount, unit) if x not in (None, "")).strip() or None
        session.add(FertilizationLog(date=today, fertilizer_name=product,
                                    amount_used=amount_used,
                                    notes=payload.get("notes") or None,
                                    plant_id=plant.id))
        return f"Fed {plant.variety_name} ({product})."

    if kind == "harvest":
        plant = _need_plant(session, payload)
        qty = payload.get("amount")
        try:
            qty = max(1, round(float(qty))) if qty is not None else 1
        except (TypeError, ValueError):
            qty = 1
        session.add(Harvest(plant_id=plant.id, date=today, quantity=qty,
                            notes=payload.get("notes") or None))
        return f"Harvested {qty} from {plant.variety_name}."

    if kind == "pest":
        plant = _need_plant(session, payload)
        pest = (payload.get("detail") or "").strip()
        if not pest:
            raise DraftApplyError("Name the pest first.")
        session.add(PestLog(date=today, pest_name=pest, plant_id=plant.id,
                            notes=payload.get("notes") or None))
        return f"Logged {pest} on {plant.variety_name}."

    if kind in ("observe", "note"):
        plant = _need_plant(session, payload)
        session.add(ObservationLog(
            plant_id=plant.id, plant_name=plant.variety_name, date=today,
            notes=(payload.get("notes") or "").strip() or "(no note)",
            health_scale=7))
        return f"Noted on {plant.variety_name}."

    if kind == "seed":
        variety = (payload.get("plant_name") or "").strip()
        if not variety:
            raise DraftApplyError("Name the variety for this seed packet.")
        year = payload.get("seed_year")
        try:
            year = int(year) if year not in (None, "") else None
        except (TypeError, ValueError):
            year = None
        count = payload.get("amount")
        try:
            count = max(1, round(float(count))) if count not in (None, "") else None
        except (TypeError, ValueError):
            count = None
        session.add(SeedPacket(
            variety_name=variety,
            species_type=(payload.get("seed_species") or "").strip(),
            vendor_name=(payload.get("seed_vendor") or "").strip(),
            year_acquired=year, seed_count=count,
            notes=payload.get("notes") or None, date_added=today))
        return f"Added {variety} to the seed stash."

    if kind == "plant_status":
        plant = _need_plant(session, payload)
        status = (payload.get("detail") or "").replace("→", "").strip()
        if status not in ("Growing", "Harvested", "Done", "Planned"):
            raise DraftApplyError("Pick a valid status first.")
        plant.status = status
        session.add(plant)
        return f"{plant.variety_name} → {status}."

    if kind == "plant_move":
        plant = _need_plant(session, payload)
        dest_id = payload.get("to_container_id")
        dest = session.get(Container, dest_id) if dest_id else None
        if dest is None:
            raise DraftApplyError("Pick a destination container first.")
        year = Date.today().year
        old = None
        if payload.get("planting_id"):
            old = session.get(Planting, payload["planting_id"])
        if old is not None:
            session.delete(old)
        session.add(Planting(container_id=dest.id, plant_id=plant.id,
                             season_year=year))
        return f"Moved {plant.variety_name} to {dest.name}."

    if kind == "reminder":
        title = (payload.get("reminder_title") or "").strip()
        due = (payload.get("reminder_due") or "").strip()
        if not title or not due:
            raise DraftApplyError("Reminders need a title and a date.")
        session.add(UserReminder(title=title[:200], due_date=due,
                                 notes=payload.get("notes") or None))
        return f"Reminder set: {title} ({due})."

    if kind == "chaos_reroll":
        from app import chaos as chaos_mod

        variety = (payload.get("plant_name") or "").strip()
        if not variety:
            raise DraftApplyError("No chaos variety was drawn.")
        chaos_mod.reroll(session, Date.today().year, pinned=variety)
        return f"🎲 Chaos pick is now {variety}."

    if kind == "memory_write":
        which = (payload.get("memory_file") or "").strip()
        addition = (payload.get("memory_addition") or "").strip()
        if which not in AGENT_FILES or not addition:
            raise DraftApplyError("That memory draft was unreadable.")
        row = session.get(AgentFile, which)
        if row is None:
            row = AgentFile(name=which, content="")
        base = (row.content or "").rstrip()
        row.content = (base + "\n- " + addition + "\n") if base else ("- " + addition + "\n")
        row.updated_at = datetime.now()
        session.add(row)
        return f"Remembered in {which}."

    raise DraftApplyError(f"Unknown draft kind '{kind}' — discard it and ask again.")


@router.post("/drafts/{draft_id}/confirm")
def confirm_draft(draft_id: int,
                  session: Session = Depends(get_session)) -> dict:
    """Apply one draft after the gardener's OK, then remove it."""
    draft = _draft_or_404(session, draft_id)
    try:
        summary = apply_draft(session, draft)
    except DraftApplyError as e:
        raise HTTPException(400, str(e))
    session.delete(draft)
    session.commit()
    return {"ok": True, "summary": summary}


@router.post("/drafts/{draft_id}/discard")
def discard_draft(draft_id: int,
                  session: Session = Depends(get_session)) -> dict:
    draft = _draft_or_404(session, draft_id)
    session.delete(draft)
    session.commit()
    return {"ok": True}


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: int,
                 session: Session = Depends(get_session)) -> dict:
    return discard_draft(draft_id, session)
