"""Scoped bearer tokens for programmatic API access (Hermes, scripts).

Verdant's web UI needs no credentials — the local-trust model stands. The
rule for tokens is simple:

- No ``Authorization`` header  →  the request passes through exactly as today.
- ``Authorization: Bearer <token>`` present  →  the token must be valid
  (known hash, not revoked) and must carry every scope the endpoint needs,
  otherwise 401 (bad/unknown/revoked token) or 403 (valid token, wrong scopes).

Token secrets are ``verdant_`` + 32 urlsafe bytes, generated server-side and
shown ONCE at creation. Only the SHA-256 hex digest is stored.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import ApiToken, utcnow

TOKEN_PREFIX = "verdant_"

# The full scope vocabulary lives here so it's easy to extend when Hermes
# reports what it actually needs. "*" is full control; "read" covers every
# GET; "<domain>:write" covers POST/PUT/PATCH/DELETE for that domain.
SCOPES: tuple[str, ...] = (
    "*",
    "read",
    "invoices:write",
    "seed_packets:write",
    "plants:write",
    "harvests:write",
    "expenses:write",
    "observations:write",
    "watering:write",
)

SCOPE_DESCRIPTIONS: dict[str, str] = {
    "*": "Full control — every endpoint, read and write.",
    "read": "Read everything (all GET endpoints).",
    "invoices:write": "Create, edit, delete invoices (incl. receipt scan + packet links).",
    "seed_packets:write": "Create, edit, delete seed packets (incl. photos).",
    "plants:write": "Create, edit, delete plants.",
    "harvests:write": "Log, edit, delete harvests.",
    "expenses:write": "Create, edit, delete expenses.",
    "observations:write": "Log, edit, delete observations (incl. photos).",
    "watering:write": "Log, edit, delete watering & fertilization logs.",
}

# Domains whose router gets GET→read / mutating→<domain>:write via require_domain().
DOMAIN_SCOPES: dict[str, str] = {
    "invoices": "invoices:write",
    "seed_packets": "seed_packets:write",
    "plants": "plants:write",
    "harvests": "harvests:write",
    "expenses": "expenses:write",
    "observations": "observations:write",
    "watering_logs": "watering:write",
    "fertilizations": "watering:write",
}

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def hash_token(secret: str) -> str:
    """SHA-256 hex digest of a token secret. The secret itself is never stored."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """A new token secret. Shown once at creation, then only the hash is kept."""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def _bearer_secret(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if not auth:
        return None
    scheme, _, secret = auth.partition(" ")
    if scheme.lower() != "bearer" or not secret.strip():
        return None
    return secret.strip()


def _lookup_token(session: Session, secret: str) -> Optional[ApiToken]:
    return session.exec(
        select(ApiToken).where(ApiToken.token_hash == hash_token(secret))
    ).first()


def authenticate(request: Request, session: Session) -> Optional[set[str]]:
    """Validate the Bearer token on the request.

    Returns the token's scope set, or None when no Authorization header is
    present (local UI passthrough). Raises 401 for a present-but-invalid,
    unknown, or revoked token. Touches last_used_at on success.
    """
    secret = _bearer_secret(request)
    if secret is None:
        return None
    token = _lookup_token(session, secret)
    if token is None or token.revoked:
        raise HTTPException(status_code=401, detail="Invalid or revoked API token.")
    token.last_used_at = utcnow()
    session.add(token)
    session.commit()
    return set(token.scopes)


def check_scopes(granted: set[str], needed: tuple[str, ...]) -> None:
    """Raise 403 unless the granted scopes cover every needed scope (or "*")."""
    if "*" in granted:
        return
    missing = [s for s in needed if s not in granted]
    if missing:
        raise HTTPException(
            status_code=403,
            detail=f"Token is missing required scope(s): {', '.join(missing)}.",
        )


def _enforce(request: Request, session: Session, needed: tuple[str, ...]) -> None:
    scopes = authenticate(request, session)
    if scopes is None:
        return  # no header: the web UI passes through untouched
    check_scopes(scopes, needed)


def require_scopes(*needed: str):
    """Dependency factory: the listed scopes (or "*") are required — but only
    when an Authorization header is present. Headerless requests (the web UI)
    are allowed through exactly as before."""

    async def _dep(request: Request, session: Session = Depends(get_session)) -> None:
        _enforce(request, session, needed)

    return _dep


def require_domain(domain: str):
    """Router-level dependency: GET/HEAD/OPTIONS need ``read``; every other
    method needs the domain's write scope. Headerless requests pass through."""

    async def _dep(request: Request, session: Session = Depends(get_session)) -> None:
        needed = ("read",) if request.method in _READ_METHODS else (DOMAIN_SCOPES[domain],)
        _enforce(request, session, needed)

    return _dep


def get_token_scopes(request: Request, session: Session) -> Optional[set[str]]:
    """Dependency returning the caller's scope set, or None for headerless
    (local UI) requests. Raises 401 on a bad token."""
    return authenticate(request, session)


# --------------------------------------------------------------------------- #
# Token management endpoints (used by the Settings page UI)
# --------------------------------------------------------------------------- #
router = APIRouter(prefix="/api/api-tokens", tags=["api-tokens"])


class TokenCreate(BaseModel):
    name: str
    scopes: List[str] = []


class TokenRead(BaseModel):
    id: int
    name: str
    scopes: List[str]
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    revoked: bool = False


def _read(token: ApiToken) -> TokenRead:
    return TokenRead(
        id=token.id,
        name=token.name,
        scopes=token.scopes,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        revoked=token.revoked,
    )


@router.get("/scopes", response_model=List[dict])
def list_scopes() -> List[dict]:
    """The scope vocabulary, for the Settings page checkboxes."""
    return [{"scope": s, "description": SCOPE_DESCRIPTIONS[s]} for s in SCOPES]


@router.get("/", response_model=List[TokenRead])
def list_tokens(session: Session = Depends(get_session)) -> List[TokenRead]:
    tokens = session.exec(select(ApiToken).order_by(ApiToken.created_at.desc())).all()
    return [_read(t) for t in tokens]


@router.post("/", response_model=dict, status_code=201)
def create_token(payload: TokenCreate, session: Session = Depends(get_session)) -> dict:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the token a name first.")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="Keep the name under 80 characters.")
    scopes = [s for s in (payload.scopes or []) if isinstance(s, str)]
    unknown = [s for s in scopes if s not in SCOPES]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown scope(s): {', '.join(unknown)}."
        )
    secret = generate_token()
    token = ApiToken(
        name=name,
        token_hash=hash_token(secret),
        scopes_json=json.dumps(sorted(set(scopes))),
    )
    session.add(token)
    session.commit()
    session.refresh(token)
    # The plaintext secret is returned exactly once, right here.
    return {"token": _read(token), "secret": secret}


@router.post("/{token_id}/revoke", response_model=dict)
def revoke_token(token_id: int, session: Session = Depends(get_session)) -> dict:
    token = session.get(ApiToken, token_id)
    if token is None:
        raise HTTPException(status_code=404, detail=f"Token {token_id} not found.")
    token.revoked = True
    session.add(token)
    session.commit()
    return {"ok": True, "token": _read(token)}
