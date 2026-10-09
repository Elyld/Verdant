"""SQLModel table definitions for the Gardening Blog & Observation Log."""

import re
import secrets
from datetime import date as Date
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import sqlalchemy as sa
from fastapi import HTTPException
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
    amount_used: Optional[str] = None  # legacy free text ("2 tbsp / gal"), kept for display
    # Structured amount going forward: numeric value + unit (tsp, tbsp, oz, cup, ml, L, gal).
    amount_value: Optional[float] = None
    amount_unit: Optional[str] = Field(default="")
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
    # Unit the weight was recorded in. Always set on write (form default "oz",
    # auto-derived when unit itself is a weight unit); blank/legacy rows read as oz.
    # Nullable per the codebase convention (see _relax_not_null_constraints).
    weight_unit: Optional[str] = Field(default="oz")
    notes: Optional[str] = None
    plant: Optional[Plant] = Relationship(back_populates="harvests")


# --------------------------------------------------------------------------- #
# Preservation & pantry — what happened to the harvest after picking day.
# A PreservationLog is the event ("canned 12 lbs of tomatoes"); PantryItem
# rows are what's still on the shelf, decremented as they're used up.
# --------------------------------------------------------------------------- #
class PreservationLog(SQLModel, table=True):
    __tablename__ = "preservation_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    preservation_id: str = Field(
        default_factory=lambda: f"PRES-{uuid4().hex[:8].upper()}",
        unique=True, index=True,
    )
    date: str = Field(index=True, default="")  # ISO YYYY-MM-DD
    # canned | frozen | dehydrated | fermented | gave_away | fresh
    method: str = Field(default="frozen", index=True)
    variety_name: str = Field(default="", index=True)
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    harvest_id: Optional[int] = Field(default=None, foreign_key="harvests.id", index=True)
    qty_in: Optional[float] = None
    qty_in_unit: Optional[str] = Field(default="")
    qty_out: Optional[float] = None
    qty_out_unit: Optional[str] = Field(default="")
    stored_location: Optional[str] = Field(default="")  # "freezer", "pantry shelf"
    notes: Optional[str] = None

    plant: Optional["Plant"] = Relationship()


class PantryItem(SQLModel, table=True):
    __tablename__ = "pantry_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)  # "Canned Cherokee Purple tomatoes"
    method: str = Field(default="", index=True)  # mirrors PreservationLog.method
    quantity: float = Field(default=0)
    unit: str = Field(default="")
    stored_date: str = Field(default="", index=True)  # ISO YYYY-MM-DD
    location: Optional[str] = Field(default="")
    notes: Optional[str] = None
    preservation_id: Optional[int] = Field(
        default=None, foreign_key="preservation_logs.id", index=True
    )

    preservation: Optional[PreservationLog] = Relationship()


class WateringLog(SQLModel, table=True):
    __tablename__ = "watering_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    watering_id: str = Field(default_factory=lambda: f"WATER-{uuid4().hex[:8].upper()}", unique=True, index=True)
    location_id: Optional[int] = Field(default=None, foreign_key="locations.id", index=True, ondelete="CASCADE")
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    date: str = Field(index=True, default="")
    method: Optional[str] = None
    amount: Optional[str] = None  # legacy free text, kept for display
    # Structured amount going forward: numeric value + unit (gal, L, qt, ml...).
    amount_value: Optional[float] = None
    amount_unit: Optional[str] = Field(default="")
    notes: Optional[str] = None
    location: Optional[Location] = Relationship()

# --------------------------------------------------------------------------- #
# Costs
# --------------------------------------------------------------------------- #
class Expense(SQLModel, table=True):
    __tablename__ = "expenses"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True, default="")  # ISO YYYY-MM-DD
    category: str = Field(default="Supplies", index=True)  # Seeds, Soil, Fertilizer, Tools, Plants, Supplies, Other
    description: str = Field(default="")
    amount: float = Field(default=0.0)  # dollars
    notes: Optional[str] = None
    # Optional: tie a purchase to a plant so the season scorecard can split
    # costs per variety (e.g. that 10-gal bag of soil was for the Habanero).
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)

    plant: Optional["Plant"] = Relationship()


# --------------------------------------------------------------------------- #
# Invoices
# --------------------------------------------------------------------------- #
class Invoice(SQLModel, table=True):
    """A purchase invoice / order receipt, usually from a seed or garden supplier.

    Lives on the Costs page next to the expenses it backs up. Invoices can be
    entered by hand, imported from CSV, or pulled from order-confirmation
    emails (source="gmail"). An invoice may link to the Expense row it
    documents via expense_id.
    """

    __tablename__ = "invoices"

    id: Optional[int] = Field(default=None, primary_key=True)
    vendor: str = Field(default="", index=True)
    order_date: str = Field(index=True, default="")  # ISO YYYY-MM-DD
    order_number: str = Field(default="", index=True)
    total: float = Field(default=0.0)  # dollars
    items_summary: Optional[str] = None  # short human-readable list of what was ordered
    pdf_path: Optional[str] = None  # /uploads/invoices/<id>/xxxx.pdf
    notes: Optional[str] = None
    # Deep link back to the source email this invoice came from (e.g. a Gmail
    # permalink). Set when source="gmail"; the Costs page renders it as a link.
    email_link: Optional[str] = None
    source: str = Field(default="manual")  # manual | csv | gmail
    expense_id: Optional[int] = Field(default=None, foreign_key="expenses.id", index=True)
    # True when the linked expense was auto-created from this invoice (see
    # app/invoice_expenses.py). Auto-created expenses are synced and deleted
    # along with the invoice; manually linked ones are left alone.
    expense_auto_created: bool = Field(default=False)

    expense: Optional["Expense"] = Relationship()


# --------------------------------------------------------------------------- #
# Invoice <-> seed packet links (which packets came from which order)
# --------------------------------------------------------------------------- #
class InvoiceSeedPacket(SQLModel, table=True):
    """Many-to-many link between an invoice and the seed packets it bought.

    Composite primary key keeps the pair unique; both sides cascade so
    deleting an invoice (or a packet) drops its links automatically.
    """

    __tablename__ = "invoice_seed_packets"

    invoice_id: int = Field(foreign_key="invoices.id", primary_key=True, index=True, ondelete="CASCADE")
    seed_packet_id: int = Field(foreign_key="seed_packets.id", primary_key=True, index=True, ondelete="CASCADE")


# --------------------------------------------------------------------------- #
# Expense <-> seed packet links (which packets an expense bought)
# --------------------------------------------------------------------------- #
class ExpenseSeedPacket(SQLModel, table=True):
    """Many-to-many link between an expense and the seed packets it bought.

    Composite primary key keeps the pair unique; both sides cascade so
    deleting an expense (or a packet) drops its links automatically.
    Independent from invoice links: tagging an invoice never tags its
    expense and vice versa.
    """

    __tablename__ = "expense_seed_packets"

    expense_id: int = Field(foreign_key="expenses.id", primary_key=True, index=True, ondelete="CASCADE")
    seed_packet_id: int = Field(foreign_key="seed_packets.id", primary_key=True, index=True, ondelete="CASCADE")


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
    # Structured seed count going forward (enables inventory math, e.g. decrement on sow).
    seed_count: Optional[int] = Field(default=None, ge=0)
    photo_path: str = Field(default="")  # /uploads/... packet photo (front)
    photo_back_path: str = Field(default="")  # /uploads/... packet photo (back, growing info)
    # "Grow again?" rating for the winter order assistant: "" (unrated),
    # "no" (skip), "yes" (grow again), "favorite" (must grow).
    grow_again: str = Field(default="", max_length=16)
    notes: Optional[str] = None
    date_added: str = Field(default="", index=True)  # ISO YYYY-MM-DD

    vendor: Optional["SeedSource"] = Relationship()


# --------------------------------------------------------------------------- #
# Seed wishlist — varieties to buy on the next winter seed order
# --------------------------------------------------------------------------- #
class WishlistItem(SQLModel, table=True):
    __tablename__ = "wishlist_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    variety_name: str = Field(index=True)
    vendor_name: str = Field(default="")  # where it was bought / will be bought
    notes: Optional[str] = None
    checked: bool = Field(default=False)  # ticked for the next order
    date_added: str = Field(default="", index=True)  # ISO YYYY-MM-DD


# --------------------------------------------------------------------------- #
# Dated reminders set via the AI chat ("remind me to plant carrots on Oct 12")
# --------------------------------------------------------------------------- #
class UserReminder(SQLModel, table=True):
    __tablename__ = "user_reminders"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str  # what to be reminded about
    due_date: str = Field(index=True, default="")  # ISO YYYY-MM-DD
    notes: Optional[str] = None
    done: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)


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
    size: str = Field(default="")  # free text, e.g. "4x8 ft" for beds
    # Structured volume for pots/bags/planters (number + unit: gal, qt, L).
    volume_value: Optional[float] = None
    volume_unit: Optional[str] = Field(default="")
    # Height in feet, used by the 3D planner view (arches default to 7).
    height_ft: Optional[float] = Field(default=None)
    location_id: Optional[int] = Field(default=None, foreign_key="locations.id", index=True)
    season_year: int = Field(index=True)
    x: float = Field(default=10.0)  # legacy canvas position, 0-100 (superseded by grid_*)
    y: float = Field(default=10.0)
    # Grid placement: cell coordinates (top-left) and footprint in cells.
    # Null until backfilled from the legacy x/y on first read.
    grid_x: Optional[int] = Field(default=None)
    grid_y: Optional[int] = Field(default=None)
    grid_w: Optional[int] = Field(default=None)
    grid_h: Optional[int] = Field(default=None)
    plant_id: Optional[int] = Field(default=None, foreign_key="plants.id", index=True)
    soil_notes: str = Field(default="")

    plant: Optional["Plant"] = Relationship()
    location: Optional["Location"] = Relationship()


# --------------------------------------------------------------------------- #
# Plantings — which plants grow in a container in a season (many per container)
# --------------------------------------------------------------------------- #
class Planting(SQLModel, table=True):
    __tablename__ = "plantings"

    id: Optional[int] = Field(default=None, primary_key=True)
    container_id: int = Field(foreign_key="containers.id", index=True)
    plant_id: int = Field(foreign_key="plants.id", index=True)
    season_year: int = Field(index=True)
    slot: int = Field(default=0)  # position within the container (row/slot number)
    notes: str = Field(default="")

    container: Optional["Container"] = Relationship()
    plant: Optional["Plant"] = Relationship()


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


# --------------------------------------------------------------------------- #
# PATCH helper
# --------------------------------------------------------------------------- #
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _coerce_patch_value(key: str, value: Any, col: sa.Column) -> Any:
    """Coerce one PATCH value to its column type; 422 on garbage."""
    if value is None:
        if col.nullable:
            return None
        raise HTTPException(422, f"{key}: null is not allowed here.")
    col_type = col.type
    if isinstance(col_type, sa.Date):
        if isinstance(value, Date):
            return value
        text = str(value).strip()
        try:
            return Date.fromisoformat(text)
        except ValueError:
            raise HTTPException(422, f"{key}: {value!r} is not a valid YYYY-MM-DD date.")
    if isinstance(col_type, sa.Boolean):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "yes"):
            return True
        if text in ("false", "0", "no"):
            return False
        raise HTTPException(422, f"{key}: {value!r} is not true/false.")
    if isinstance(col_type, sa.Integer):
        if isinstance(value, bool):
            raise HTTPException(422, f"{key}: {value!r} is not a whole number.")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            raise HTTPException(422, f"{key}: {value!r} is not a whole number.")
        try:
            return int(str(value).strip())
        except (ValueError, TypeError):
            raise HTTPException(422, f"{key}: {value!r} is not a whole number.")
    if isinstance(col_type, (sa.Float, sa.Numeric)):
        if isinstance(value, bool):
            raise HTTPException(422, f"{key}: {value!r} is not a number.")
        if isinstance(value, (int, float)):
            return value
        try:
            return float(str(value).strip())
        except (ValueError, TypeError):
            raise HTTPException(422, f"{key}: {value!r} is not a number.")
    # String columns. Dates are stored as ISO strings by convention, so a
    # date object becomes ISO and a non-empty date-ish string must parse.
    if isinstance(value, Date) and (key == "date" or key.endswith("_date")):
        return value.isoformat()
    if isinstance(value, str) and (key == "date" or key.endswith("_date")):
        text = value.strip()
        if text and not _ISO_DATE_RE.match(text):
            raise HTTPException(422, f"{key}: {value!r} is not a valid YYYY-MM-DD date.")
        try:
            if text:
                Date.fromisoformat(text)
        except ValueError:
            raise HTTPException(422, f"{key}: {value!r} is not a valid YYYY-MM-DD date.")
        return text
    return value


def apply_patch(obj: SQLModel, payload: Dict[str, Any], exclude: tuple = ()) -> None:
    """Apply a JSON PATCH payload onto a table row, safely.

    Only real table columns are assigned: relationship names (``plant``,
    ``images``…) and unknown keys are ignored instead of poisoning the
    session and 500ing at commit. Primary keys and any ``exclude``d public
    IDs (``harvest_id``…) are protected from overwrite. Values are coerced
    to the column's type — ISO ``YYYY-MM-DD`` for Date columns, numbers
    for Integer/Float columns — raising ``HTTPException`` 422 on bad
    input instead of storing garbage that 500s on later reads.

    The object is expected to be attached to the caller's session; the
    caller commits.
    """
    table = type(obj).__table__
    excluded = set(exclude)
    for key, value in payload.items():
        if key not in table.columns:
            continue  # relationship name or unknown key: ignore, don't 500
        col = table.columns[key]
        if col.primary_key or key in excluded:
            continue
        setattr(obj, key, _coerce_patch_value(key, value, col))


# --------------------------------------------------------------------------- #
# Agent self — the chat assistant's persistent identity, memory, threads, drafts
# --------------------------------------------------------------------------- #
# The assistant is no longer a stateless chatbot: it keeps three text files
# (persona / operating_notes / memory — its soul.md, agents.md, memory.md),
# full conversation threads, and every confirm-before-save draft server-side,
# so a browser refresh never loses progress.

AGENT_FILES = ("persona", "operating_notes", "memory")


class AgentFile(SQLModel, table=True):
    __tablename__ = "agent_files"

    name: str = Field(primary_key=True, max_length=32)  # one of AGENT_FILES
    content: str = Field(default="")
    updated_at: datetime = Field(default_factory=utcnow)


class AgentConversation(SQLModel, table=True):
    __tablename__ = "agent_conversations"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(default="New chat", max_length=120)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AgentMessage(SQLModel, table=True):
    __tablename__ = "agent_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(
        foreign_key="agent_conversations.id", index=True, ondelete="CASCADE")
    role: str = Field(max_length=16)  # "user" | "assistant"
    content: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class AgentDraft(SQLModel, table=True):
    __tablename__ = "agent_drafts"

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: Optional[int] = Field(
        default=None, foreign_key="agent_conversations.id", index=True,
        ondelete="CASCADE")
    kind: str = Field(max_length=32, index=True)  # water | fertilize | … | chaos_reroll | memory_write
    payload_json: str = Field(default="{}")  # the draft dict the UI confirms
    created_at: datetime = Field(default_factory=utcnow)
