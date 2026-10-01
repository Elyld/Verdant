"""LLM provider abstraction for Verdant's AI features.

Two providers, one interface:
- "ollama": a model server on the user's own machine (Ollama-compatible
  /api/chat). Nothing leaves the local network.
- "openrouter": OpenRouter's OpenAI-compatible cloud API
  (https://openrouter.ai/api/v1). The user's API key lives in Verdant's own
  settings table on their own server — it is never returned by the API.

All AI features (the /api/ai/* endpoints) go through chat()/status() here,
so adding a provider never means touching every feature.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from app import frost as frost_mod

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_OLLAMA_BASE = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:4b"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"

PROVIDERS = ("ollama", "openrouter")


class LLMError(Exception):
    """A friendly, show-the-user failure from the model provider."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


def _normalize_base_url(raw: str) -> str:
    """Normalize the Ollama base URL.

    The app appends /api/tags and /api/chat itself, so a user-supplied
    trailing /v1 (an OpenAI-style habit) would break every call — strip it.
    """
    base = (raw or "").strip().rstrip("/")
    if base.lower().endswith("/v1"):
        base = base[: -len("/v1")].rstrip("/")
    return base or DEFAULT_OLLAMA_BASE


def get_config(session) -> dict:
    """Resolve the AI config from settings. Never includes the API key."""
    provider = (frost_mod.get_setting(session, "ai_provider") or "ollama").strip().lower()
    if provider not in PROVIDERS:
        provider = "ollama"
    return {
        "enabled": (frost_mod.get_setting(session, "local_ai_enabled") or "false") == "true",
        "provider": provider,
        "ollama_base_url": _normalize_base_url(
            frost_mod.get_setting(session, "local_ai_base_url") or DEFAULT_OLLAMA_BASE
        ),
        "ollama_model": (frost_mod.get_setting(session, "local_ai_model") or DEFAULT_OLLAMA_MODEL).strip(),
        "openrouter_model": (
            frost_mod.get_setting(session, "openrouter_model") or DEFAULT_OPENROUTER_MODEL
        ).strip(),
        "openrouter_key_set": bool(frost_mod.get_setting(session, "openrouter_api_key")),
    }


def _openrouter_key(session) -> str:
    return (frost_mod.get_setting(session, "openrouter_api_key") or "").strip()


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _is_timeout(exc: Exception) -> bool:
    """Did this failure come from a socket timeout (possibly wrapped in URLError)?"""
    if isinstance(exc, TimeoutError):  # socket.timeout is an alias since 3.10
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    return "timed out" in str(reason or exc).lower()


def _get_json(url: str, timeout: int, headers: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "verdant-garden-log", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, timeout: int, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "verdant-garden-log",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_error_detail(e: Exception) -> str:
    """What the server actually said, for HTTPError responses."""
    detail = f"{type(e).__name__}: {e}".strip()
    if isinstance(e, urllib.error.HTTPError):
        try:
            said = e.read().decode("utf-8", "replace").strip()[:300]
            if said:
                # OpenRouter nests it: {"error": {"message": "..."}}
                try:
                    said_json = json.loads(said)
                    msg = (said_json.get("error") or {}).get("message")
                    if msg:
                        said = str(msg)[:300]
                except (ValueError, AttributeError):
                    pass
                detail += f" — server said: {said}"
        except Exception:
            pass
    return detail


# --------------------------------------------------------------------------- #
# Provider calls
# --------------------------------------------------------------------------- #
def _ollama_chat(base_url: str, model: str, messages: list[dict],
                 json_mode: bool, timeout: int) -> str:
    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
    }
    if json_mode:
        payload["format"] = "json"
    try:
        body = _post_json(f"{base_url}/api/chat", payload, timeout=timeout)
        return ((body.get("message") or {}).get("content")) or ""
    except Exception as e:
        detail = _http_error_detail(e)
        hint = ""
        if "localhost" in base_url or "127.0.0.1" in base_url:
            hint = (" Verdant runs in Docker, so localhost means the Verdant container itself — "
                    "use http://host.docker.internal:11434 to reach Ollama on the same machine, "
                    "and set OLLAMA_HOST=0.0.0.0 so Ollama accepts the connection.")
        extra = ""
        if _is_timeout(e):
            # cold model loads are slow; don't give up too early
            extra = (" The model didn't answer in time — it may still be loading "
                     "(cold starts are slow). Wait a few seconds and try again.")
        raise LLMError(
            f"Couldn't reach the model at {base_url} ({detail}).{extra}",
            hint.strip(),
        )


def _openrouter_chat(api_key: str, model: str, messages: list[dict],
                     json_mode: bool, timeout: int) -> str:
    payload: dict = {"model": model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/elyld/Verdant",
        "X-Title": "Verdant Garden Journal",
    }
    try:
        body = _post_json(f"{OPENROUTER_BASE}/chat/completions", payload,
                          timeout=timeout, headers=headers)
    except Exception as e:
        detail = _http_error_detail(e)
        hint = ""
        if isinstance(e, urllib.error.HTTPError) and e.code == 401:
            hint = "That looks like a bad or expired API key — check it on the Settings page."
        elif isinstance(e, urllib.error.HTTPError) and e.code == 402:
            hint = "OpenRouter says this key is out of credits — top up at openrouter.ai."
        raise LLMError(f"OpenRouter didn't complete the request ({detail}).", hint)
    try:
        return (body["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise LLMError("OpenRouter answered, but not in a shape I understand.")


def chat(session, messages: list[dict], *, json_mode: bool = False,
         timeout: int | None = None) -> str:
    """Send messages to the configured provider. Returns the assistant text.

    Raises LLMError with a user-friendly message on any failure.
    """
    cfg = get_config(session)
    if not cfg["enabled"]:
        raise LLMError("AI is off — enable it on the Settings page first.")
    if cfg["provider"] == "openrouter":
        key = _openrouter_key(session)
        if not key:
            raise LLMError("OpenRouter is selected but there's no API key — add one on the Settings page.")
        return _openrouter_chat(key, cfg["openrouter_model"], messages,
                                json_mode, timeout or 60)
    return _ollama_chat(cfg["ollama_base_url"], cfg["ollama_model"], messages,
                        json_mode, timeout or 120)


def status(session) -> dict:
    """Is the feature on, and is the provider reachable? Never raises."""
    cfg = get_config(session)
    if not cfg["enabled"]:
        return {"enabled": False, "provider": cfg["provider"], "reachable": False}
    if cfg["provider"] == "openrouter":
        return openrouter_status(session)
    return _ollama_status(cfg)


def _ollama_status(cfg: dict) -> dict:
    try:
        # /api/tags is GET-only on Ollama (POST → 405).
        body = _get_json(f"{cfg['ollama_base_url']}/api/tags", timeout=5)
        models = [m.get("name") for m in (body.get("models") or []) if isinstance(m, dict)]
        want = cfg["ollama_model"]
        present = any(
            m == want or (m and want and m.split(":")[0] == want.split(":")[0])
            for m in models
        )
        return {"enabled": True, "provider": "ollama", "reachable": True,
                "model": want, "model_present": present, "models": models}
    except Exception as e:
        hint = f"Could not reach {cfg['ollama_base_url']} — is the model server running?"
        if "localhost" in cfg["ollama_base_url"] or "127.0.0.1" in cfg["ollama_base_url"]:
            hint += (" Verdant runs in Docker, so localhost means the Verdant container itself — "
                     "use http://host.docker.internal:11434 to reach Ollama on the same machine, "
                     "and set OLLAMA_HOST=0.0.0.0 so Ollama accepts the connection.")
        # Surface the raw failure so the Test connection button can show it:
        # "refused" = nothing listening (Ollama down or bound to 127.0.0.1),
        # "timed out" = firewall/routing, name-resolution errors = bad hostname.
        detail = _http_error_detail(e)
        return {"enabled": True, "provider": "ollama", "reachable": False,
                "model": cfg["ollama_model"], "hint": hint, "error": detail[:300]}


def openrouter_status(session) -> dict:
    """Validate the OpenRouter key via the free auth/key endpoint. Never raises."""
    cfg = get_config(session)
    key = _openrouter_key(session)
    if not key:
        return {"enabled": True, "provider": "openrouter", "reachable": False,
                "model": cfg["openrouter_model"],
                "hint": "No OpenRouter API key saved — add one on the Settings page."}
    try:
        body = _get_json(
            f"{OPENROUTER_BASE}/auth/key", timeout=10,
            headers={"Authorization": f"Bearer {key}"},
        )
        data = body.get("data") or {}
        return {"enabled": True, "provider": "openrouter", "reachable": True,
                "model": cfg["openrouter_model"],
                "key_label": data.get("label"),
                "key_usage_usd": data.get("usage"),
                }
    except Exception as e:
        detail = _http_error_detail(e)
        hint = "OpenRouter didn't accept the request."
        if isinstance(e, urllib.error.HTTPError) and e.code == 401:
            hint = "OpenRouter rejected the API key — check it on the Settings page."
        return {"enabled": True, "provider": "openrouter", "reachable": False,
                "model": cfg["openrouter_model"], "hint": hint, "error": detail[:300]}
