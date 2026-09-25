"""SQLModel table definitions for the Gardening Blog & Observation Log."""

from datetime import date as Date
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Blog
# --------------------------------------------------------------------------- #
class PostImage(SQLModel, table=True):
    __tablename__ = "post_images"

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="posts.id", index=True, ondelete="CASCADE")
    file_path: str
    uploaded_at: datetime = Field(default_factory=utcnow)

    post: Optional["Post"] = Relationship(back_populates="images")


class Post(SQLModel, table=True):
    __tablename__ = "posts"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    content: str = ""  # markdown
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)

    images: List[PostImage] = Relationship(
        back_populates="post",
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "PostImage.id"},
    )


# --------------------------------------------------------------------------- #
# Fertilization
# --------------------------------------------------------------------------- #
class FertilizationLog(SQLModel, table=True):
    __tablename__ = "fertilization_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True, default="")
    fertilizer_name: str = Field(index=True)  # keep for backward compat
    fertilizer_id: Optional[int] = Field(default=None, foreign_key="fertilizers.id", index=True)
    npk_ratio: Optional[str] = None
    amount_used: Optional[str] = None
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    location_id: Optional[int] = Field(default=None, foreign_key="locations.id", index=True)
    notes: Optional[str] = None
    fertilizer: Optional["Fertilizer"] = Relationship(back_populates="fertilization_logs")
    plant: Optional["Plant"] = Relationship(back_populates="fertilization_logs")



# --------------------------------------------------------------------------- #
# Observations
# --------------------------------------------------------------------------- #
class ObservationImage(SQLModel, table=True):
    __tablename__ = "observation_images"

    id: Optional[int] = Field(default=None, primary_key=True)
    observation_id: int = Field(
        foreign_key="observation_logs.id", index=True, ondelete="CASCADE"
    )
    file_path: str
    uploaded_at: datetime = Field(default_factory=utcnow)

    observation: Optional["ObservationLog"] = Relationship(back_populates="images")


class ObservationLog(SQLModel, table=True):
    __tablename__ = "observation_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True, default="")
    plant_name: str = Field(index=True)  # keep for backward compat
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    health_scale: int = Field(default=5, ge=1, le=10)
    watering_status: bool = Field(default=True)
    pest_sightings: Optional[str] = None
    notes: Optional[str] = None
    # Weather snapshot captured automatically at log time (Open-Meteo, optional).
    temp_c: Optional[float] = None
    weather_summary: Optional[str] = None
    plant: Optional["Plant"] = Relationship(back_populates="observation_logs")
    images: List[ObservationImage] = Relationship(
        back_populates="observation",
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "ObservationImage.id"},
    )


# --------------------------------------------------------------------------- #
# Albums (imported photo collections, e.g. "2026 Garden")
# --------------------------------------------------------------------------- #
class Album(SQLModel, table=True):
    __tablename__ = "albums"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)
    source_url: str = ""  # e.g. "immich:<album-id>" for Immich imports (enables metadata re-sync)

    images: List["AlbumImage"] = Relationship(
        back_populates="album",
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "AlbumImage.id"},
    )


class AlbumImage(SQLModel, table=True):
    __tablename__ = "album_images"

    id: Optional[int] = Field(default=None, primary_key=True)
    album_id: int = Field(foreign_key="albums.id", index=True, ondelete="CASCADE")
    file_path: str
    title: str = ""
    original_name: str = ""
    source_url: str = ""
    imported_at: datetime = Field(default_factory=utcnow)
    # Photo metadata pulled from Immich EXIF (populated on import or via sync).
    taken_at: Optional[datetime] = None
    camera_make: str = ""
    camera_model: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    album: Optional["Album"] = Relationship(back_populates="images")

class Location(SQLModel, table=True):
    __tablename__ = "locations"
    id: Optional[int] = Field(default=None, primary_key=True)
    location_id: str = Field(default_factory=lambda: f"LOC-{uuid4().hex[:8].upper()}", unique=True, index=True)
    name: str = Field(index=True)
    type: str = Field(default="Container")
    light: str = Field(default="Full Sun")
    pot_size: Optional[str] = None
    notes: Optional[str] = None
    plants: List["Plant"] = Relationship(back_populates="location", cascade_delete=True)

class Plant(SQLModel, table=True):
    __tablename__ = "plants"
    id: Optional[int] = Field(default=None, primary_key=True)
    plant_id: str = Field(default_factory=lambda: f"PLANT-{uuid4().hex[:8].upper()}", unique=True, index=True)
    variety_name: str = Field(index=True)
    species_type: str
    family_genus: Optional[str] = None
    category: str = Field(default="Annual")
    status: str = Field(default="Growing")
    location_id: Optional[int] = Field(default=None, foreign_key="locations.id", index=True)
    date_started_indoors: Optional[Date] = None
    date_planted: Optional[Date] = None
    days_to_maturity: Optional[int] = None
    light: str = Field(default="Full Sun")
    pot_size: Optional[str] = None
    notes: Optional[str] = None
    # Care cadence (days) — drives watering/feeding reminders. Null = no reminder.
    water_every_days: Optional[int] = Field(default=None, ge=1, le=365)
    feed_every_days: Optional[int] = Field(default=None, ge=1, le=365)
    location: Optional[Location] = Relationship(back_populates="plants")
    fertilization_logs: List["FertilizationLog"] = Relationship(back_populates="plant")
    observation_logs: List["ObservationLog"] = Relationship(back_populates="plant")
    harvests: List["Harvest"] = Relationship(back_populates="plant")

class Fertilizer(SQLModel, table=True):
    __tablename__ = "fertilizers"
    id: Optional[int] = Field(default=None, primary_key=True)
    fertilizer_id: str = Field(unique=True, index=True)
    name: str = Field(index=True)
    npk_ratio: Optional[str] = None
    best_for: Optional[str] = None
    notes: Optional[str] = None
    fertilization_logs: List["FertilizationLog"] = Relationship(back_populates="fertilizer")

class SeedSource(SQLModel, table=True):
    __tablename__ = "seed_sources"
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: str = Field(unique=True, index=True)
    source: str = Field(index=True)
    variety: str = Field(default="")  # optional: sometimes only the vendor is known
    type: str = Field(default="Vendor Purchase")
    acquired_date: Optional[Date] = None
    linked_plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    notes: Optional[str] = None

class Harvest(SQLModel, table=True):
    __tablename__ = "harvests"
    id: Optional[int] = Field(default=None, primary_key=True)
    harvest_id: str = Field(default_factory=lambda: f"HARV-{uuid4().hex[:8].upper()}", unique=True, index=True)
    plant_id: int = Field(foreign_key="plants.id", index=True, ondelete="CASCADE")
    date: str = Field(index=True, default="")
    quantity: int
    unit: str = Field(default="fruit")
    weight: Optional[float] = None
    notes: Optional[str] = None
    plant: Optional[Plant] = Relationship(back_populates="harvests")

class WateringLog(SQLModel, table=True):
    __tablename__ = "watering_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    watering_id: str = Field(default_factory=lambda: f"WATER-{uuid4().hex[:8].upper()}", unique=True, index=True)
    location_id: Optional[int] = Field(default=None, foreign_key="locations.id", index=True, ondelete="CASCADE")
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    date: str = Field(index=True, default="")
    method: Optional[str] = None
    amount: Optional[str] = None
    notes: Optional[str] = None
    location: Optional[Location] = Relationship()