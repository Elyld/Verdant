"""Gardening Blog & Observation Log — FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import UPLOAD_DIR, init_db
from app.routers import albums, fertilizations, immich, observations, posts, stats
from app.version import __version__

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Gardening Blog & Observation Log",
    description="Self-hosted garden journal: blog posts with photos, fertilization and observation logs.",
    version=__version__,
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
app.include_router(albums.router)
app.include_router(immich.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


# Uploaded images and the SPA assets.
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ───────────────────────────── Routes ─────────────────────────────

# Per-route HTML pages — each renders its own standalone template.
# No SPA JavaScript tab switching needed; plain links handle navigation.

@app.get("/", include_in_schema=False)
def blog_home() -> HTMLResponse:
    """ Blog & stories homepage with post creation form. """
    return templates.TemplateResponse("blog.html", {"request": {}, "__version__": __version__})


@app.get("/observations", include_in_schema=False)
def observations_page() -> HTMLResponse:
    """ Observation logging and history page. """
    return templates.TemplateResponse("observations.html", {"request": {}, "__version__": __version__})


@app.get("/calendar", include_in_schema=False)
def calendar_page() -> HTMLResponse:
    """ Calendar view page. """
    return templates.TemplateResponse("calendar.html", {"request": {}, "__version__": __version__})