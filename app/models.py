"""SQLModel table definitions for the Gardening Blog & Observation Log."""

import secrets
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
    # XMP/keyword tags from Immich (comma-separated). Immich ingests XMP
    # sidecar keywords as tags, so this is where sideloaded XMP data lands.
    tags: str = ""
    # The plant this photo shows, assigned by hand on the /match page.
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)

    album: Optional["Album"] = Relationship(back_populates="images")
    plant: Optional["Plant"] = Relationship(back_populates="album_images")

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
    album_images: List["AlbumImage"] = Relationship(back_populates="plant")

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

# --------------------------------------------------------------------------- #
# Costs
# --------------------------------------------------------------------------- #
class Expense(SQLModel, table=True):
    __tablename__ = "expenses"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True, default="")  # ISO YYYY-MM-DD
    category: str = Field(default="Supplies", index=True)  # Seeds, Soil, Fertilizer, Tools, Plants, Other
    description: str = Field(default="")
    amount: float = Field(default=0.0)  # dollars
    notes: Optional[str] = None
    # Optional: tie a purchase to a plant so the season scorecard can split
    # costs per variety (e.g. that 10-gal bag of soil was for the Habanero).
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)

    plant: Optional["Plant"] = Relationship()


# --------------------------------------------------------------------------- #
# Pests
# --------------------------------------------------------------------------- #
class PestLog(SQLModel, table=True):
    __tablename__ = "pest_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True, default="")  # ISO YYYY-MM-DD
    pest_name: str = Field(default="", index=True)
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    treatment: Optional[str] = None
    notes: Optional[str] = None
    resolved: bool = Field(default=False)

    plant: Optional[Plant] = Relationship()


# --------------------------------------------------------------------------- #
# App settings (key/value store backing the /settings page)
# --------------------------------------------------------------------------- #
class Setting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True, max_length=64)
    value: str = Field(default="", max_length=2000)


# --------------------------------------------------------------------------- #
# Seed packets — the seed stash inventory (what's in the binder)
# --------------------------------------------------------------------------- #
class SeedPacket(SQLModel, table=True):
    __tablename__ = "seed_packets"

    id: Optional[int] = Field(default=None, primary_key=True)
    packet_id: str = Field(
        default_factory=lambda: f"SEEDPK-{uuid4().hex[:8].upper()}",
        unique=True, index=True,
    )
    variety_name: str = Field(index=True)
    species_type: str = Field(default="")
    category: str = Field(default="", index=True)  # Pepper, Tomato, Herb, Flower...
    vendor_id: Optional[int] = Field(default=None, foreign_key="seed_sources.id", index=True)
    vendor_name: str = Field(default="", index=True)  # plain vendor name (v2.10.1+: no more vendor repeats)
    vendor_url: str = Field(default="")  # direct link to the vendor / product page
    year_acquired: Optional[int] = Field(default=None, index=True)
    quantity: str = Field(default="")  # "~40 seeds", "1 packet", ...
    photo_path: str = Field(default="")  # /uploads/... packet photo (front)
    photo_back_path: str = Field(default="")  # /uploads/... packet photo (back, growing info)
    notes: Optional[str] = None
    date_added: str = Field(default="", index=True)  # ISO YYYY-MM-DD

    vendor: Optional["SeedSource"] = Relationship()


# --------------------------------------------------------------------------- #
# NFC garden tags — tap a tag, jump straight to the right screen
# --------------------------------------------------------------------------- #
# Actions: plant (open plant profile), quick_plant (quick-log for a plant),
# fertilize (log feeding with fertilizer pre-selected), pest (pest log with
# product pre-filled), harvest (quick-log harvest stepper), location
# (quick-log filtered to a location), seed_add (seed catalog add form),
# water (quick-log watering for a location).
class GardenTag(SQLModel, table=True):
    __tablename__ = "garden_tags"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(
        default_factory=lambda: secrets.token_urlsafe(6),
        unique=True, index=True,
    )
    label: str = Field(index=True)  # "Neem oil bottle"
    action: str = Field(index=True)
    target_id: Optional[int] = Field(default=None, index=True)
    target_text: str = Field(default="")  # freeform target, e.g. a product name
    tap_count: int = Field(default=0)
    last_tapped_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# Containers — the backyard builder: grow bags, raised beds, pots, planters
# --------------------------------------------------------------------------- #
class Container(SQLModel, table=True):
    __tablename__ = "containers"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)  # "Grow bag 3"
    kind: str = Field(default="grow bag", index=True)  # grow bag, raised bed, pot, planter
    size: str = Field(default="")  # "10 gal", "4x8 ft"
    location_id: Optional[int] = Field(default=None, foreign_key="locations.id", index=True)
    season_year: int = Field(index=True)
    x: float = Field(default=10.0)  # canvas position, 0-100
    y: float = Field(default=10.0)
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    soil_notes: str = Field(default="")

    plant: Optional["Plant"] = Relationship()
    location: Optional["Location"] = Relationship()


class SeedlingBatch(SQLModel, table=True):
    """One indoor seed-starting batch: a variety sown on a date, in a tray and setup.

    The workstation for the indoor season — trays on warming mats, under lights —
    tracking everything from sow to transplant so next year's setup repeats what worked.
    """
    __tablename__ = "seedling_batches"

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: str = Field(
        default_factory=lambda: f"SEEDL-{uuid4().hex[:8].upper()}",
        unique=True, index=True,
    )
    variety_name: str = Field(index=True)
    packet_id: Optional[int] = Field(default=None, index=True)  # link to the seed stash packet used
    sow_date: str = Field(default="", index=True)  # ISO YYYY-MM-DD
    tray: str = Field(default="")        # "Tray A", "1020 #2"
    location: str = Field(default="")    # "basement shelf", "spare room"
    heat_mat: bool = Field(default=False)
    grow_light: str = Field(default="")  # "LED shop light, 16h/day"
    cells_sown: Optional[int] = Field(default=None)
    germinated: int = Field(default=0)
    germination_date: str = Field(default="")  # ISO, first sprout spotted
    status: str = Field(default="sowing", index=True)
    # sowing → germinating → growing → hardening → transplanted → finished | failed
    transplant_date: str = Field(default="")  # ISO
    notes: str = Field(default="")
