"""Observation log CRUD + image uploads."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import ObservationImage, ObservationLog
from app.schemas import (
    ObservationCreate,
    ObservationRead,
    ObservationUpdate,
    UploadResult,
)
from app.storage import delete_stored, save_uploads

router = APIRouter(prefix="/api/observations", tags=["observations"])


def _get_or_404(session: Session, obs_id: int) -> ObservationLog:
    obs = session.get(ObservationLog, obs_id)
    if obs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Observation not found")
    return obs


@router.get("", response_model=List[ObservationRead])
def list_observations(
    session: Session = Depends(get_session),
    plant: Optional[str] = Query(default=None, description="Filter by plant name"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[ObservationLog]:
    stmt = select(ObservationLog)
    if plant:
        stmt = stmt.where(func.lower(ObservationLog.plant_name).like(f"%{plant.lower()}%"))
    stmt = (
        stmt.order_by(ObservationLog.date.desc(), ObservationLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


@router.post("", response_model=ObservationRead, status_code=status.HTTP_201_CREATED)
def create_observation(
    payload: ObservationCreate, session: Session = Depends(get_session)
) -> ObservationLog:
    obs = ObservationLog(**payload.model_dump())
    obs.plant_name = obs.plant_name.strip()
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return obs


@router.get("/{obs_id}", response_model=ObservationRead)
def get_observation(obs_id: int, session: Session = Depends(get_session)) -> ObservationLog:
    return _get_or_404(session, obs_id)


@router.patch("/{obs_id}", response_model=ObservationRead)
def update_observation(
    obs_id: int, payload: ObservationUpdate, session: Session = Depends(get_session)
) -> ObservationLog:
    obs = _get_or_404(session, obs_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(obs, key, value)
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return obs


@router.delete("/{obs_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_observation(obs_id: int, session: Session = Depends(get_session)) -> None:
    obs = _get_or_404(session, obs_id)
    paths = [img.file_path for img in obs.images]
    session.delete(obs)
    session.commit()
    for path in paths:
        delete_stored(path)


@router.post(
    "/{obs_id}/images", response_model=UploadResult, status_code=status.HTTP_201_CREATED
)
async def upload_observation_images(
    obs_id: int,
    files: List[UploadFile] = File(..., description="One or more image files"),
    session: Session = Depends(get_session),
) -> UploadResult:
    obs = _get_or_404(session, obs_id)
    urls = await save_uploads(files, f"observations/{obs_id}")
    if not urls:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No image files received")

    images = [ObservationImage(observation_id=obs.id, file_path=url) for url in urls]
    session.add_all(images)
    session.commit()
    for img in images:
        session.refresh(img)
    return UploadResult(images=images)


@router.delete("/{obs_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_observation_image(
    obs_id: int, image_id: int, session: Session = Depends(get_session)
) -> None:
    image = session.get(ObservationImage, image_id)
    if image is None or image.observation_id != obs_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Image not found")
    path = image.file_path
    session.delete(image)
    session.commit()
    delete_stored(path)
