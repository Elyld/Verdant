"""Pydantic request/response schemas (API contract, decoupled from tables)."""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    uploaded_at: datetime


# ------------------------------- Blog posts -------------------------------- #
class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = ""


class PostUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = None


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    images: List[ImageRead] = []


# ---------------------------- Fertilization logs --------------------------- #
class FertilizationCreate(BaseModel):
    date: Date
    fertilizer_name: str = Field(min_length=1, max_length=120)
    npk_ratio: str = Field(default="", max_length=40)
    amount_used: str = Field(default="", max_length=80)
    notes: str = ""


class FertilizationUpdate(BaseModel):
    date: Optional[Date] = None
    fertilizer_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    npk_ratio: Optional[str] = Field(default=None, max_length=40)
    amount_used: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = None


class FertilizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: Date
    fertilizer_name: str
    npk_ratio: str
    amount_used: str
    notes: str


# ----------------------------- Observation logs ---------------------------- #
class ObservationCreate(BaseModel):
    date: Date
    plant_name: str = Field(min_length=1, max_length=120)
    health_scale: int = Field(default=5, ge=1, le=10)
    watering_status: bool = False
    pest_sightings: str = ""
    notes: str = ""


class ObservationUpdate(BaseModel):
    date: Optional[Date] = None
    plant_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    health_scale: Optional[int] = Field(default=None, ge=1, le=10)
    watering_status: Optional[bool] = None
    pest_sightings: Optional[str] = None
    notes: Optional[str] = None


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: Date
    plant_name: str
    health_scale: int
    watering_status: bool
    pest_sightings: str
    notes: str
    images: List[ImageRead] = []


# --------------------------------- Misc ------------------------------------ #
class UploadResult(BaseModel):
    images: List[ImageRead]


class Stats(BaseModel):
    posts: int
    fertilizations: int
    observations: int
    images: int
    avg_health: Optional[float] = None
    last_watered: Optional[Date] = None


class CalendarEntry(BaseModel):
    id: int
    date: Date
    plant_name: str
    health_scale: int
    watering_status: bool
    pest_sightings: str
    notes: str


# --------------------------------- Albums --------------------------------- #
class AlbumImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    title: str
    original_name: str
    source_url: str
    imported_at: datetime


class AlbumImageRef(BaseModel):
    """Reference to an already-imported album image (for copying into posts)."""

    image_id: int
    title: str = ""


class AlbumRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    images: List[AlbumImageRead] = []


class AlbumCreateResult(BaseModel):
    album: AlbumRead
    created: int
    failed: int
    errors: List[str] = []


class AlbumImportFromAlbum(BaseModel):
    album_id: int
    image_ids: List[int]


class ImportFromUrlRequest(BaseModel):
    urls: List[str] = Field(min_length=1)
    album_id: Optional[int] = None
