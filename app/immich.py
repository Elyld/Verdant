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


def list_album_assets(album_id: str) -> List[dict]:
    """Fetch every asset in an album via the metadata search endpoint.

    Immich v3 removed the embedded ``assets`` array from
    ``GET /api/albums/{id}`` (it now only returns ``assetCount``), so album
    contents must come from ``POST /api/search/metadata`` filtered by
    ``albumIds``. That endpoint exists on older servers too, so this works
    across versions. Results are paginated; follow ``nextPage`` until done.
    """
    assets: List[dict] = []
    page: object = 1
    with _client() as c:
        while True:
            try:
                resp = c.post(
                    "/api/search/metadata",
                    json={"albumIds": [album_id], "withExif": True, "page": page, "size": 1000},
                )
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail=f"Could not reach Immich: {exc}",
                ) from exc
            _raise_for(resp)
            block = (resp.json() or {}).get("assets") or {}
            assets.extend(block.get("items") or [])
            nxt = block.get("nextPage")
            if not nxt:
                break
            page = nxt
    return assets


def download_asset(asset_id: str, thumbnail: bool = False) -> bytes:
    """Fetch original (or thumbnail) bytes for one asset."""
    path = f"/api/assets/{asset_id}/thumbnail" if thumbnail else f"/api/assets/{asset_id}/original"
    with _client() as c:
        try:
            resp = c.get(path, params={"size": "preview"} if thumbnail else None)
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach Immich: {exc}") from exc
        if resp.status_code == 403 and not thumbnail:
            # Listing albums only needs asset.view, but downloading originals
            # needs the separate asset.download permission. Without it every
            # import silently imports 0 photos, so say exactly what to fix.
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Immich refused the download (403). The API key needs the "
                    "'asset.download' permission: in Immich, open Account settings "
                    "-> API keys -> edit this key -> tick 'asset.download' -> save, "
                    "then retry the import."
                ),
            )
        _raise_for(resp)
        return resp.content
