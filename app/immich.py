"""Minimal Immich API client (albums + asset download).

Configured via env vars:
- IMMICH_BASE_URL   e.g. http://192.168.0.50:2283  (no trailing slash needed)
- IMMICH_API_KEY    an Immich API key (Account Settings -> API Keys)

Only what the garden log needs: list albums, list an album's assets, and
download an asset's original bytes. No writes to Immich are ever made.
"""
from __future__ import annotations

import os
from typing import List, Optional

import httpx
from fastapi import HTTPException, status


def _config() -> tuple[str, str]:
    base = (os.getenv("IMMICH_BASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("IMMICH_API_KEY") or "").strip()
    if not base or not key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Immich isn't configured. Set IMMICH_BASE_URL and IMMICH_API_KEY.",
        )
    return base, key


def _client() -> httpx.Client:
    base, key = _config()
    return httpx.Client(
        base_url=base,
        headers={"x-api-key": key, "Accept": "application/json"},
        timeout=httpx.Timeout(20.0, connect=8.0),
    )


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code == 401:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Immich rejected the API key.")
    if resp.status_code == 404:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found on Immich.")
    if resp.is_error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Immich returned {resp.status_code}: {resp.text[:200]}",
        )


def list_albums() -> List[dict]:
    with _client() as c:
        try:
            resp = c.get("/api/albums")
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach Immich: {exc}") from exc
        _raise_for(resp)
        return resp.json()


def get_album(album_id: str) -> dict:
    with _client() as c:
        try:
            resp = c.get(f"/api/albums/{album_id}")
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach Immich: {exc}") from exc
        _raise_for(resp)
        return resp.json()


def download_asset(asset_id: str, thumbnail: bool = False) -> bytes:
    """Fetch original (or thumbnail) bytes for one asset."""
    path = f"/api/assets/{asset_id}/thumbnail" if thumbnail else f"/api/assets/{asset_id}/original"
    with _client() as c:
        try:
            resp = c.get(path, params={"size": "preview"} if thumbnail else None)
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach Immich: {exc}") from exc
        _raise_for(resp)
        return resp.content
