"""Pydantic request/response schemas (API contract, decoupled from tables)."""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _none_to_str(value):
    """Coerce NULLs from old databases to "" so reads never 500."""
    return "" if value is None else value


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
    plant_id: Optional[int] = None
    location_id: Optional[int] = None


class FertilizationUpdate(BaseModel):
    date: Optional[Date] = None
    fertilizer_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    npk_ratio: Optional[str] = Field(default=None, max_length=40)
    amount_used: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = None
    fertilizer_id: Optional[int] = None
    plant_id: Optional[int] = None
    location_id: Optional[int] = None


class FertilizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: Date
    fertilizer_name: str
    npk_ratio: str
    amount_used: str
    notes: str
    fertilizer_id: Optional[int] = None
    plant_id: Optional[int] = None
    location_id: Optional[int] = None

    _null_str = field_validator("npk_ratio", "amount_used", "notes", mode="before")(_none_to_str)


# ----------------------------- Observation logs ---------------------------- #
class ObservationCreate(BaseModel):
    date: Date
    plant_name: str = Field(min_length=1, max_length=120)
    plant_id: Optional[int] = None
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
    plant_id: Optional[int] = None


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: Date
    plant_name: str
    health_scale: int
    watering_status: bool
    pest_sightings: Optional[str] = ""
    notes: str
    images: List[ImageRead] = []
    plant_id: Optional[int] = None
    temp_c: Optional[float] = None
    weather_summary: Optional[str] = None

    _null_str = field_validator("notes", mode="before")(_none_to_str)


# --------------------------------- Plants ---------------------------------- #
class ReminderRead(BaseModel):
    plant_id: int
    plant_name: str
    kind: str  # "water" | "feed"
    last_date: Optional[Date] = None
    due_date: Optional[Date] = None
    days_until_due: Optional[int] = None  # negative = overdue
    status: str  # "overdue" | "due" | "soon" | "ok" | "unset"


class TimelineEvent(BaseModel):
    kind: str  # "observation" | "fertilization" | "harvest" | "watering"
    date: Date
    id: int
    title: str
    detail: str = ""
    health_scale: Optional[int] = None
    images: List[ImageRead] = []


class TimelapsePhoto(BaseModel):
    file_path: str
    date: Date
    caption: str = ""


class PlantTimelineRead(BaseModel):
    plant_id: int
    plant_name: str
    events: List[TimelineEvent] = []
    photos: List[TimelapsePhoto] = []  # chronological, for the timelapse player


# --------------------------------- Harvests -------------------------------- #
class HarvestCreate(BaseModel):
    plant_id: int
    date: Date
    quantity: int = Field(ge=1)
    unit: str = Field(default="fruit", max_length=40)
    weight: Optional[float] = Field(default=None, ge=0)
    notes: str = ""


class WateringCreate(BaseModel):
    location_id: Optional[int] = None
    plant_id: Optional[int] = None
    date: Date
    method: str = ""
    amount: str = ""
    notes: str = ""


# ------------------------------ Season review ------------------------------ #
class TopPlant(BaseModel):
    plant_name: str
    observations: int


class ReviewRead(BaseModel):
    year: int
    observations: int
    observations_by_month: List[int]
    avg_health_by_month: List[Optional[float]]
    harvest_count: int
    harvest_weight: Optional[float] = None
    photos: int
    pests_noted: int
    waterings: int
    feedings: int
    top_plants: List[TopPlant] = []
    busiest_day: Optional[Date] = None
    busiest_day_count: int = 0


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
    pest_sightings: Optional[str] = None
    notes: Optional[str] = None


# --------------------------------- Albums --------------------------------- #
class AlbumImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    title: str
    original_name: str
    source_url: str
    imported_at: datetime
    taken_at: Optional[datetime] = None
    camera_make: str = ""
    camera_model: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    tags: str = ""
    plant_id: Optional[int] = None
    # Filled in by endpoints that join plants; not a model column.
    plant_variety: Optional[str] = None

    _null_str = field_validator(
        "source_url", "camera_make", "camera_model", "tags", mode="before"
    )(_none_to_str)


class AlbumImageRef(BaseModel):
    """Reference to an already-imported album image (for copying into posts)."""

    image_id: int
    title: str = ""


class AlbumRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    source_url: str = ""
    images: List[AlbumImageRead] = []

    _null_str = field_validator("source_url", mode="before")(_none_to_str)


class AlbumMetadataSyncResult(BaseModel):
    album_id: int
    total: int
    updated: int


class AlbumMergeResult(BaseModel):
    """Outcome of merging local albums that point at the same Immich album."""

    groups_merged: int
    albums_removed: int
    images_moved: int
    files_removed: int
    detail: List[str] = []


class ImageAssignRequest(BaseModel):
    """Assign a photo to a plant (or unassign with null)."""

    plant_id: Optional[int] = None


class ImageBulkAssignRequest(BaseModel):
    """Assign many photos to one plant at once (null unassigns)."""

    image_ids: List[int] = Field(min_length=1, max_length=2000)
    plant_id: Optional[int] = None


class AlbumCreateResult(BaseModel):
    album: AlbumRead
    created: int
    failed: int
    errors: List[str] = []


class ImmichBatchImportResult(BaseModel):
    """One batch of an Immich album import. The client repeats the request
    with increasing offset until done is true."""

    album_id: int
    album_name: str
    total: int  # photo assets in the Immich album
    imported: int  # photos in the local album so far
    done: bool
    created: int  # photos added by this batch
    failed: int
    errors: List[str] = []


class AlbumImportFromAlbum(BaseModel):
    album_id: int
    image_ids: List[int]


class ImportFromUrlRequest(BaseModel):
    urls: List[str] = Field(min_length=1)
    album_id: Optional[int] = None


# --------------------------------- Expenses -------------------------------- #
EXPENSE_CATEGORIES = ["Seeds", "Soil", "Fertilizer", "Tools", "Plants", "Other"]


class ExpenseCreate(BaseModel):
    date: Date
    category: str = Field(default="Supplies", max_length=40)
    description: str = Field(default="", max_length=200)
    amount: float = Field(default=0.0, ge=0)
    notes: str = ""


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: Date
    category: str
    description: str
    amount: float
    notes: str = ""

    _null_str = field_validator("description", "notes", mode="before")(_none_to_str)


# --------------------------------- Pest log -------------------------------- #
class PestLogCreate(BaseModel):
    date: Date
    pest_name: str = Field(min_length=1, max_length=120)
    plant_id: Optional[int] = None
    treatment: str = ""
    notes: str = ""


class PestLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: Date
    pest_name: str
    plant_id: Optional[int] = None
    treatment: str = ""
    notes: str = ""
    resolved: bool = False

    _null_str = field_validator("treatment", "notes", mode="before")(_none_to_str)


# ------------------------------ Yield & sowing ------------------------------ #
class YieldRow(BaseModel):
    plant_id: int
    variety_name: str
    total_quantity: int
    harvest_count: int
    unit: str


class SowRow(BaseModel):
    plant_id: int
    variety_name: str
    category: str
    suggested_start: Date
    days_until: int
    started_indoors: Optional[Date] = None
