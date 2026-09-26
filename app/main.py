"""Gardening Blog & Observation Log — FastAPI application entrypoint."""
from __future__ import annotations

from app.routers.locations import router as locations_router
from app.routers.plants import router as plants_router
from app.routers.fertilizers import router as fertilizers_router
from app.routers.seed_sources import router as seed_sources_router
from app.routers.harvests import router as harvests_router
from app.routers.watering_logs import router as watering_logs_router
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import UPLOAD_DIR, init_db
from app.models import GardenTag, utcnow
from app.routers import albums, backup, containers, digest, expenses, fertilizations, immich, import_csv, observations, pests, posts, seed_packets, settings as settings_router, stats, tags
from app.routers.tags import tag_destination
from app.version import __version__

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.digest_scheduler = _maybe_start_digest_scheduler()
    settings_router.register_digest_rescheduler(_reschedule_digest_scheduler)
    yield
    sched = app.state.digest_scheduler
    if sched is not None:
        sched.shutdown(wait=False)


def _reschedule_digest_scheduler():
    """Re-arm the morning digest after settings change (called from /api/settings)."""
    old = app.state.digest_scheduler
    if old is not None:
        old.shutdown(wait=False)
    app.state.digest_scheduler = _maybe_start_digest_scheduler()


def _maybe_start_digest_scheduler():
    """Start the daily Discord digest if enabled and a webhook is set.

    Reads the effective config (settings page wins over env vars).
    """
    import logging

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from sqlmodel import Session

    from app.database import engine
    from app.routers.digest import effective_digest_config, run_digest

    log = logging.getLogger("verdant.digest")
    with Session(engine) as session:
        cfg = effective_digest_config(session)
    if not cfg.enabled:
        return None
    if not cfg.webhook_url:
        log.warning("Digest enabled but no webhook URL is set; digest not scheduled.")
        return None
    try:
        hour, minute = (int(x) for x in cfg.time.split(":"))
    except ValueError:
        log.warning("Bad digest time %r (want HH:MM); digest not scheduled.", cfg.time)
        return None

    def _job():
        try:
            with Session(engine) as session:
                # Read fresh each run so settings-page edits apply immediately.
                live = effective_digest_config(session)
                if not live.enabled or not live.webhook_url:
                    return
                run_digest(session, live.webhook_url)
        except Exception:
            log.exception("Scheduled digest failed.")

    local_tz = datetime.now().astimezone().tzinfo
    scheduler = BackgroundScheduler(timezone=local_tz)
    scheduler.add_job(_job, CronTrigger(hour=hour, minute=minute), id="morning-digest")
    scheduler.start()
    log.info("Morning digest scheduled daily at %02d:%02d (%s).", hour, minute, local_tz)
    return scheduler


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
app.include_router(locations_router)
app.include_router(plants_router)
app.include_router(fertilizers_router)
app.include_router(seed_sources_router)
app.include_router(harvests_router)
app.include_router(watering_logs_router)
app.include_router(backup.router)
app.include_router(digest.router)
app.include_router(import_csv.router)
app.include_router(expenses.router)
app.include_router(pests.router)
app.include_router(settings_router.router)
app.include_router(seed_packets.router)
app.include_router(tags.router)
app.include_router(containers.router)

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
def blog_home(request: Request) -> HTMLResponse:
    """ Blog & stories homepage with post creation form. """
    return templates.TemplateResponse(request, "blog.html", {"__version__": __version__})


@app.get("/observations", include_in_schema=False)
def observations_page(request: Request) -> HTMLResponse:
    """ Observation logging and history page. """
    return templates.TemplateResponse(request, "observations.html", {"__version__": __version__})


@app.get("/calendar", include_in_schema=False)
def calendar_page(request: Request) -> HTMLResponse:
    """ Calendar view page. """
    return templates.TemplateResponse(request, "calendar.html", {"__version__": __version__})


@app.get("/photos", include_in_schema=False)
def photos_page(request: Request) -> HTMLResponse:
    """ Photo album slideshow page. """
    return templates.TemplateResponse(request, "photos.html", {"__version__": __version__})


@app.get("/plants", include_in_schema=False)
def plants_page(request: Request) -> HTMLResponse:
    """Plant profiles: care reminders, timelines, harvests, timelapses."""
    return templates.TemplateResponse(request, "plants.html", {"__version__": __version__})


@app.get("/seeds", include_in_schema=False)
def seeds_page(request: Request) -> HTMLResponse:
    """Seed sources: vendors, saved seeds, and trades."""
    return templates.TemplateResponse(request, "seed_sources.html", {"__version__": __version__})


@app.get("/review", include_in_schema=False)
def review_page(request: Request) -> HTMLResponse:
    """Season in review: a year of garden stats."""
    return templates.TemplateResponse(request, "review.html", {"__version__": __version__})


@app.get("/backup", include_in_schema=False)
def backup_page(request: Request) -> HTMLResponse:
    """Download or restore a full backup (database + uploaded photos)."""
    return templates.TemplateResponse(request, "backup.html", {"__version__": __version__})


@app.get("/import", include_in_schema=False)
def import_page(request: Request) -> HTMLResponse:
    """Import garden data from CSV files exported by other trackers."""
    return templates.TemplateResponse(request, "import.html", {"__version__": __version__})


@app.get("/slideshow", include_in_schema=False)
def slideshow_page(request: Request) -> HTMLResponse:
    """Full-screen photo slideshow (?album=<id> to start with an album)."""
    return templates.TemplateResponse(request, "slideshow.html", {"__version__": __version__})


@app.get("/quick", include_in_schema=False)
def quick_page(request: Request) -> HTMLResponse:
    """One-tap garden logging for the phone."""
    return templates.TemplateResponse(request, "quick.html", {"__version__": __version__})


@app.get("/costs", include_in_schema=False)
def costs_page(request: Request) -> HTMLResponse:
    """Track what the garden costs."""
    return templates.TemplateResponse(request, "costs.html", {"__version__": __version__})


@app.get("/pests", include_in_schema=False)
def pests_page(request: Request) -> HTMLResponse:
    """Pest sightings and treatments."""
    return templates.TemplateResponse(request, "pests.html", {"__version__": __version__})


@app.get("/settings", include_in_schema=False)
def settings_page(request: Request) -> HTMLResponse:
    """Garden location, frost dates, and digest preferences."""
    return templates.TemplateResponse(request, "settings.html", {"__version__": __version__})


@app.get("/match", include_in_schema=False)
def match_page(request: Request) -> HTMLResponse:
    """Flip through imported photos and assign them to plants."""
    return templates.TemplateResponse(request, "match.html", {"__version__": __version__})


@app.get("/fertilizers", include_in_schema=False)
def fertilizers_page(request: Request) -> HTMLResponse:
    """Manage the fertilizer product catalog."""
    return templates.TemplateResponse(request, "fertilizers.html", {"__version__": __version__})


@app.get("/planner", include_in_schema=False)
def planner_page(request: Request) -> HTMLResponse:
    """Backyard builder: lay out containers and raised beds per season."""
    return templates.TemplateResponse(request, "planner.html", {"__version__": __version__})


@app.get("/tags", include_in_schema=False)
def tags_page(request: Request) -> HTMLResponse:
    """NFC tag manager: create tags and get the URLs to write onto them."""
    return templates.TemplateResponse(request, "tags.html", {"__version__": __version__})


@app.get("/t/{code}", include_in_schema=False)
def tap_tag(code: str, request: Request):
    """NFC tap target: /t/<code> counts the tap and redirects to the tag's action."""
    from sqlmodel import Session as SQLSession

    from app.database import engine

    with SQLSession(engine) as session:
        tag = session.query(GardenTag).filter(GardenTag.code == code).first()
        if not tag:
            return templates.TemplateResponse(
                request, "tag_missing.html", {"__version__": __version__}, status_code=404
            )
        tag.tap_count += 1
        tag.last_tapped_at = utcnow()
        session.add(tag)
        session.commit()
        return RedirectResponse(url=tag_destination(tag), status_code=302)
