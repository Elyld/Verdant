"""SQLModel table definitions for the Gardening Blog & Observation Log."""

from datetime import date as Date
from datetime import datetime, timezone
from typing import List, Optional

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
    date: Date = Field(index=True)
    fertilizer_name: str
    npk_ratio: str = ""
    amount_used: str = ""
    notes: str = ""


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
    date: Date = Field(index=True)
    plant_name: str = Field(index=True)
    health_scale: int = Field(default=5, ge=1, le=10)
    watering_status: bool = False
    pest_sightings: str = ""
    notes: str = ""

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

    album: Optional["Album"] = Relationship(back_populates="images")
