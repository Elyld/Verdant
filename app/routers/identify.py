"""Plant identification endpoint — proxy to the PlantNet API.

POST /api/identify with a photo (multipart "photo"). The user's PlantNet
API key comes from Settings; without one the endpoint explains where to
get it. A photo is only uploaded to PlantNet when the user taps Identify —
nothing here runs in the background.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session

from app import frost as frost_mod
from app import plantnet
from app.database import get_session

router = APIRouter(prefix="/api/identify", tags=["identify"])

MAX_BYTES = 12 * 1024 * 1024


@router.post("")
async def identify_plant(
    photo: UploadFile = File(...), session: Session = Depends(get_session)
) -> dict:
    api_key = (frost_mod.get_setting(session, "plantnet_api_key") or "").strip()
    if not api_key:
        raise HTTPException(
            400,
            "No PlantNet API key yet — add yours on the Settings page "
            "(free at my.plantnet.org).",
        )
    if not (photo.content_type or "").startswith("image/"):
        raise HTTPException(400, "That file isn't an image.")
    image_bytes = await photo.read()
    if not image_bytes:
        raise HTTPException(400, "Empty upload.")
    if len(image_bytes) > MAX_BYTES:
        raise HTTPException(400, "Photo is too large (max 12 MB).")
    result = plantnet.identify(
        image_bytes, photo.filename or "photo.jpg", api_key
    )
    if not result.get("ok"):
        reasons = {
            "no-key": "No PlantNet API key yet — add yours on the Settings page.",
            "unreachable": "Couldn't reach PlantNet — check your connection and try again.",
            "bad-key": "PlantNet rejected the API key — double-check it on the Settings page.",
            "rate-limited": "PlantNet's daily limit is used up — try again tomorrow.",
            "no-match": "PlantNet couldn't name that one — try a closer, well-lit photo.",
        }
        raise HTTPException(
            502, reasons.get(result.get("reason"), "Identification failed — try again.")
        )
    return result
