"""Gardening Blog & Observation Log — FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import UPLOAD_DIR, init_db
from app.routers import fertilizations, observations, posts, stats

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Gardening Blog & Observation Log",
    description="Self-hosted garden journal: blog posts with photos, fertilization and observation logs.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(posts.router)
app.include_router(fertilizations.router)
app.include_router(observations.router)
app.include_router(stats.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


# Uploaded images and the SPA assets.
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
