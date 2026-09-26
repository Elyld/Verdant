# 🌿 Verdant — Self-Hosted Garden Journal (v2.14.0)

Your garden, logged. Plant profiles with care reminders, a daily observation log
with a calendar heatmap, photo albums with slideshows, a seed stash and seedling
tracker, a drag-and-drop backyard planner, NFC tag shortcuts, harvest records,
a season-in-review dashboard with a yield-vs-spend scorecard, cost and pest
tracking, a phone-friendly quick-log page, CSV import from other trackers,
one-click backup & restore, Immich photo imports, and a morning Discord digest —
all in a single Docker container. FastAPI + SQLite, no build step, no cloud.

![Verdant calendar heatmap](docs/screenshots/calendar.png)

> **THIS IS 100% VIBE CODED.** This is just a personal project, built by
> someone with no coding knowledge. It works, it's loved, and it's a little
> feral in places. 🌱

*Screenshots below show demo data.*

## Features

### 📅 Calendar — daily log at a glance
A GitHub-style heatmap of every observation, watering, and fertilization. Click
any day to see exactly what happened: health scores, notes, pests, weather.
The homepage for your garden's daily rhythm.

### 🌱 Plants — profiles, care cadence, timelines
Every plant gets a profile: variety, species, location, planted date, days to
maturity, light needs, and custom care intervals. Verdant computes what's
**overdue, due today, or coming up** for watering and feeding. Each profile
also has a photo timeline and a per-plant timelapse view.

Photos you assign on the 🎯 Match photos page appear in a **Photos** gallery
on the plant's profile, with a lightbox on click.

![Plant profiles](docs/screenshots/plants.png)

![Plant photo gallery](docs/screenshots/plant-photos.png)

### 👀 Observations — the daily log
Log health (1–10), watering, pest sightings, and freeform notes per plant, per
day — with photos attached. New observations are automatically stamped with the
current weather at your garden (free Open-Meteo data, no API key needed).

![Observation log](docs/screenshots/observations.png)

### 📸 Photos — albums & slideshows
Albums with fullscreen slideshows. Upload directly, import from a URL, pull
images into blog posts, or import whole albums from your Immich server
(batched, so even 600+ photo albums import without timing out). Re-importing
an album reuses its existing Verdant album instead of duplicating it, and
**🧹 Merge duplicates** folds any older double-imports into one. On the
**🎯 Match photos** page you can flip through imported photos and assign each
one to a plant — assigned photos show up in a gallery on the plant's profile.

![Photo albums](docs/screenshots/photos.png)

The 🎯 Match photos page (linked from the Photos tab) is where imported
photos get claimed: flip through them one by one, see each photo's taken
date, camera, GPS, and tags, and assign it to a plant with a keystroke.
Bulk-assign a whole day's photos at once when you already know what they are.

![Match photos to plants](docs/screenshots/match.png)

### 🌰 Seeds — sources & vendors
Track where every seed came from: vendors, trades, or saved seed. Grouped by
vendor, filterable, linkable to the plants you grew from them.

![Seed sources](docs/screenshots/seeds.png)

### 🌱 Seed stash — the binder, catalogued
Every packet you own, inventoried: a photo of the packet, vendor (with link),
type, year bought, and how many seeds are left. Searchable and filterable —
stick an NFC tag on the binder and tapping it opens the "add packet" form.

![Seed stash](docs/screenshots/seed-stash.png)

![Packet front/back flip](docs/screenshots/packet-flip.png)

### ✍️ Blog — garden stories
Markdown blog posts with photo galleries, for the season's stories — first
harvests, experiments, lessons learned.

![Blog](docs/screenshots/blog.png)

### 📊 Season Review — your year in the garden
Totals, averages, best days, most productive plants — a year-end (or
anytime) dashboard of everything you grew and logged. The **🏆 yield
leaderboard** keeps weighed and counted harvests on separate boards (all
weights converted to ounces, so grams never get added to ounces), and the
**⚖️ Season scorecard** answers "was it worth growing?": yield vs. spending
per variety, ranked — tag purchases to a plant on the Costs page to split
costs per variety.

![Season review](docs/screenshots/review.png)

![Season scorecard](docs/screenshots/scorecard.png)

### 🗺️ Backyard Planner — build your backyard
Lay out your actual growing space: grow bags, raised beds, pots, planters —
sized, positioned where they really sit, with a plant assigned to each.
Drag containers around the canvas (positions save automatically), copy last
season's layout into the new year and shuffle things around.

![Backyard planner](docs/screenshots/planner.png)

### 🏷️ NFC Tags — tap it, log it
Blank NFC tags turn physical things into shortcuts: tap the fertilizer
bottle and the feeding form opens with that fertilizer pre-selected; tap the
seed binder and the "add packet" form opens; tap a grow bag and that plant's
profile opens. The Tags page manages every tag — write its URL onto a blank
tag once with any NFC writer app, then your phone opens it with a tap, no
app needed.

![NFC tags](docs/screenshots/tags.png)

### 🧪 Fertilizers — the shelf
Your fertilizer products live here now: name, NPK ratio, what each is best
for. The Garden Logs feeding form suggests from the shelf, and NFC tags can
point straight at a bottle.

![Fertilizers](docs/screenshots/fertilizers.png)

### 🌱 Seedlings — the indoor workstation
Start seeds inside without losing track: every batch records variety, tray,
location, warming mat, and grow light, with a stage pipeline from sowing to
transplant and one-tap sprout logging. Germination progress bars (including
days-to-sprout) show what's working, and a nudge flags batches that go quiet
for three weeks. Finished batches keep their stats so next year's setup
repeats what worked.

![Seedlings](docs/screenshots/seedlings.png)

### ⚡ Quick Log — log it from the garden
A phone-first page for when you're standing in the garden with dirty hands:
one-tap watering per location ("Water all"), a harvest +/− stepper, and
today's entries at a glance. NFC tags can drop you straight here.

![Quick Log](docs/screenshots/quick.png)

### 💰 Costs — was it worth growing?
Every garden expense in one place, broken down by category. Tag a purchase
to a plant and the Season Review scorecard splits costs per variety, so you
can finally answer whether the peppers beat the grocery store.

![Costs](docs/screenshots/costs.png)

### 🐛 Pests — the treatment log
What showed up, what you sprayed or squashed, and whether it worked — a
running log per pest so next year's battle plan writes itself.

![Pests](docs/screenshots/pests.png)

### 📥 CSV Import — bring your own data
Moving from another garden tracker? The **Import** page (nav bar → Import)
walks you through it: pick what you're importing (locations, plants,
fertilizers, seed sources, watering logs, fertilization logs, harvests),
upload the CSV, review a preview with row counts and warnings, then import.
Imports are idempotent — re-running the same file skips what's already there,
so you'll never get duplicates.

![CSV import](docs/screenshots/import.png)

See [Importing from CSV](#importing-from-csv) below for the expected columns.

### 💾 Backup & Restore — the whole garden in a zip
One click downloads a zip containing the full database plus every uploaded
photo — or uncheck the photos box for a small, fast database-only backup.
Restoring is the reverse: upload the zip, and you're back (a photo-less
backup leaves your current photos untouched). Keep one somewhere safe
before upgrades.

![Backup & restore](docs/screenshots/backup.png)

### 🌅 Morning Digest — Discord
An optional daily "morning garden check" sent to a Discord channel via webhook:
what's overdue, what's due today, what's coming up. Off by default — set
`DIGEST_ENABLED=true` and `DISCORD_WEBHOOK_URL` to turn it on.

### 🔌 Immich integration
Browse albums on your own Immich server and import their photos straight into
Verdant — no downloading and re-uploading. Needs `IMMICH_BASE_URL` and
`IMMICH_API_KEY` (see [Configuration](#configuration)).

## Quick start (Docker — recommended)

The included `docker-compose.yml` is a plug-n-play base setup — the prebuilt
image from GitHub Container Registry, two folders for your data, nothing else
to configure:

```bash
docker compose up -d
```

Open <http://localhost:3113>. Interactive API docs: <http://localhost:3113/docs>.

That's genuinely the whole setup: no `.env` file needed, no build step, and
your data lives in the `./data` and `./uploads` folders next to the compose
file, so it survives rebuilds and restarts. Paste the same file into Dockge
or Portainer and it just works there too.

### Reaching Verdant outside your LAN (Cloudflare Tunnel)

Verdant is tunnel-ready: no sign-on inside the app, Cloudflare handles
identity at the edge.

1. In the Cloudflare dashboard: **Zero Trust → Networks → Tunnels** → create
   a tunnel, add a public hostname pointing at `http://garden:8000`, and copy
   the tunnel token.
2. In `docker-compose.yml`: comment out the `ports:` block on the garden
   service (so the app is *not* on your LAN directly — only the tunnel can
   reach it), and uncomment the `cloudflared` service at the bottom.
3. In your `.env`: `TUNNEL_TOKEN=<token>` and `TUNNEL_MODE=true`.
4. `docker compose up -d`.
5. Add a **Cloudflare Access** policy (e.g. email one-time PIN) on the
   hostname — that's the sign-on, handled by Cloudflare, not Verdant.

`TUNNEL_MODE=true` flips the secure preset: HSTS header on, `/docs` off, and
the tunnel's proxy headers trusted so rate limiting sees real client IPs.
(Keep `ports:` if you still want LAN access too — the tunnel keeps working,
but LAN clients bypass Cloudflare Access.)

To change the host port, point Verdant at your Immich server, or turn on the
Discord digest, copy `.env.example` to `.env` and fill in what you need, then
re-run `docker compose up -d`.

The image (`ghcr.io/elyld/verdant:latest`, also tagged per release) is published
automatically by the `Publish Docker image` workflow on every push to `main`;
it builds for both `linux/amd64` and `linux/arm64` (handy for a Raspberry Pi).

Works great in Dockge, Portainer, or plain `docker compose`.

### Persistence

`docker-compose.yml` bind-mounts two host directories, so nothing is lost on
rebuild or restart:

| Host path   | Container path | Contents                  |
|-------------|----------------|---------------------------|
| `./data`    | `/data`        | `garden.db` (SQLite, WAL) |
| `./uploads` | `/uploads`     | Uploaded images           |

### Upgrading

Pull and recreate — your data lives in the bind-mounted folders, not the
image:

```bash
docker compose pull && docker compose up -d
```

On startup Verdant automatically adds any missing database columns, so old
databases (even v1.x) upgrade cleanly without manual migrations.

## Quick start (local, no Docker)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://localhost:8000>.

## Configuration

All optional — Verdant runs fine with none of these set. Copy `.env.example`
to `.env` (or set them in your Dockge stack) for the ones you want.

| Variable | Default | Meaning |
|----------|---------|---------|
| `GARDEN_PORT` | `3113` | Host port for the web UI (compose only) |
| `GARDEN_DATA_DIR` | `./data` | Directory holding `garden.db` |
| `GARDEN_UPLOAD_DIR` | `./uploads` | Image storage root |
| `GARDEN_DATABASE_URL` | `sqlite:///<data>/garden.db` | Full DB URL override |
| `GARDEN_PUBLIC_URL` | `http://localhost:3113` | Base URL used to resolve relative URLs in "Import from URL" |
| `IMMICH_BASE_URL` | (unset) | Your Immich server URL, e.g. `http://192.168.0.50:2283` (enables Immich import) |
| `IMMICH_API_KEY` | (unset) | Immich API key (Account Settings → API Keys). Needs `album.read`, `asset.view`, `asset.download` |
| `GARDEN_LAT` / `GARDEN_LON` | (unset) | Your garden's coordinates — stamps new observations with current weather (free Open-Meteo data, no key needed) |
| `DIGEST_ENABLED` | `false` | Set `true` to enable the morning Discord digest |
| `DISCORD_WEBHOOK_URL` | (unset) | Discord webhook URL (Server Settings → Integrations → Webhooks) |
| `DIGEST_TIME` | `08:00` | When the digest sends (24h `HH:MM`, server local time) |

### Immich tips

- If Verdant runs in Docker on the same machine as Immich, use
  `http://host.docker.internal:2283` (not a bare LAN IP) as
  `IMMICH_BASE_URL` so the container can reach back to your host.
- The API key needs **`asset.download`** in addition to `album.read` /
  `asset.view` — without it, imports list albums fine but every photo fails
  with a 403. Verdant tells you exactly this in the UI if it happens.
- Import captures each photo's **XMP keyword tags** (Immich reads XMP
  sidecars into tags) plus date taken, camera, and GPS, so the Match page can
  show you what each photo is while you assign it.

### Weather stamping

Set `GARDEN_LAT` and `GARDEN_LON` (find your coordinates by clicking your spot
on the map at <https://open-meteo.com>) and every new observation is stamped
with the temperature and conditions at log time. Free, no API key.

### Discord digest

1. In Discord: Server Settings → Integrations → Webhooks → New Webhook, pick
   a channel, copy the webhook URL.
2. Set `DIGEST_ENABLED=true`, paste the URL into `DISCORD_WEBHOOK_URL`, and
   optionally change `DIGEST_TIME`.
3. Restart. Every morning you get overdue / due-today / coming-up care tasks.
4. Test anytime: `GET /api/digest/preview` to see the message,
   `POST /api/digest/send` to send one on demand.

## Importing from CSV

The Import page (`/import`) accepts CSVs exported from other garden trackers.
Suggested order (so linked records resolve): **Locations → Plants →
Fertilizers → Seed sources → Watering → Fertilization → Harvests.**

Expected columns (headers are matched case-insensitively; extra columns are
ignored):

| Import | Columns |
|--------|---------|
| Locations | `location_id`, `name`, `type`, `light`, `notes` |
| Plants | `plant_id`, `variety_name`, `species`, `category`, `status`, `location` (name or id), `date_planted`, `date_started_indoors`, `days_to_maturity`, `light`, `notes`, `water_every_days`, `feed_every_days` |
| Fertilizers | `fertilizer_id`, `name`, `npk_ratio`, `best_for`, `notes` |
| Seed sources | `source_id`, `source`, `variety`, `type`, `acquired_date`, `notes` |
| Watering logs | `log_id`, `date`, `location`, `plant`, `method`, `amount` (parsed to number + unit when it looks like one, e.g. `2 gal`), `notes` |
| Fertilization logs | `log_id`, `date`, `fertilizer`, `npk_ratio`, `amount_used` (free text), `plant`, `notes` |
| Harvests | `harvest_id`, `date`, `plant`, `quantity`, `unit`, `weight`, `weight_unit` (oz/g/lb/kg — defaults to oz) |

Notes:

- **Preview first.** Every upload shows row counts, warnings, and sample rows
  before anything is written. Harvest rows without a recognizable plant get a
  per-row plant picker in the preview.
- **IDs are preserved.** If your CSV has IDs like `LOC-01` or `PL-042`,
  they're kept — and re-importing the same file skips existing rows instead
  of duplicating them.
- Blank rows are ignored; UTF-8 files with a BOM work fine.

## Backup & restore

**Backup:** open the Backup page (`/backup`) → Download. You get a zip with
`garden.db` and, unless you uncheck the box, the entire `uploads/` tree.
Store one before every upgrade.

**Restore:** on the same page, upload a backup zip. Verdant replaces the
database with the backup's contents; uploads are replaced too, unless the
backup was made without photos — then your current photos are left alone.

There's also a JSON export per table via the API (see `/docs`) if you'd
rather script it.

## API

Full interactive docs at `/docs` when the app is running. Highlights:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/plants` | List plant profiles (with care status) |
| `POST` | `/api/plants` | Create a plant |
| `GET/PATCH/DELETE` | `/api/plants/{id}` | Read / update / delete |
| `GET` | `/api/plants/reminders` | Overdue / due today / coming up care tasks |
| `GET/POST` | `/api/observations` | List / log an observation (+ photos) |
| `GET` | `/api/stats/calendar` | Day-by-day activity for the heatmap |
| `GET/POST` | `/api/fertilizations` | Fertilization log |
| `GET/POST` | `/api/watering` | Watering log |
| `GET/POST` | `/api/harvests` | Harvest records |
| `GET/POST` | `/api/seed-sources` | Seed sources |
| `GET/POST` | `/api/locations` | Garden locations |
| `GET/POST` | `/api/albums` | Photo albums |
| `POST` | `/api/albums/{id}/import` | Import photos (upload or URL list, batched) |
| `GET` | `/api/immich/albums` | List albums on your Immich server |
| `POST` | `/api/immich/albums/{id}/import` | Import an Immich album (batched, idempotent) |
| `POST` | `/api/import/preview` | Preview a CSV import |
| `POST` | `/api/import/run` | Run a CSV import |
| `GET` | `/api/backup/download` | Download full backup zip |
| `POST` | `/api/backup/restore` | Restore from backup zip |
| `GET` | `/api/digest/preview` | Preview the morning Discord digest |
| `POST` | `/api/digest/send` | Send the digest now |
| `GET` | `/api/stats/review` | Season-in-review aggregates |
| `GET` | `/api/health` | Healthcheck (includes version) |

## Upload security

- File type is decided by **magic bytes**, not by the client's filename or
  `Content-Type` (jpg, png, gif, webp, bmp only → otherwise `415`).
- Stored filenames are random hex, so a hostile filename cannot traverse
  directories or overwrite anything (`../../etc/passwd.png` becomes
  `/uploads/posts/3/<random>.png`).
- 8 MB cap per file, enforced while streaming; partial files are removed on failure.
- Deletes are confined to the uploads root by a resolved-path check.

## Layout

```
verdant/
├── app/
│   ├── main.py           FastAPI app, page routes, static + /uploads mounts
│   ├── version.py        single source of truth for the version
│   ├── database.py       engine, session dep, init_db (WAL, FK pragma, auto column sync)
│   ├── models.py         SQLModel tables
│   ├── schemas.py        request/response models
│   ├── storage.py        secure image save/delete
│   ├── digest.py         morning Discord digest builder
│   ├── routers/          posts, observations, plants, locations, fertilizations,
│   │                     watering, harvests, seed_sources, albums, immich,
│   │                     stats, backup, import_csv, digest
│   ├── static/           app.js (vanilla JS, no build step), styles
│   └── templates/        one standalone HTML page per tab
├── docs/screenshots/     README screenshots (demo data)
├── tests/                pytest API tests + JS unit checks
├── Dockerfile
├── docker-compose.yml    GHCR image, host volumes, healthcheck
└── .env.example          every supported setting, documented
```

Palette: **sage green**, **navy blue**, **beige** — everywhere, always.

## Data model

- **locations** — `id, location_id, name, type, light, notes`
- **plants** — `id, plant_id, variety_name, species_type, category, status, location_id, date_planted, days_to_maturity, water_every_days, feed_every_days, notes`
- **observation_logs** — `id, date, plant_id, plant_name, health_scale (1–10), watering_status, pest_sightings, notes, temp_c, weather_summary`
- **fertilization_logs** — `id, date, fertilizer_id, fertilizer_name, npk_ratio, amount_used, plant_id, notes`
- **watering_logs** — `id, date, location_id, plant_id, method, amount, notes`
- **harvests** — `id, harvest_id, date, plant_id, quantity, unit, weight_grams, notes`
- **fertilizers** — `id, fertilizer_id, name, npk_ratio, best_for, notes`
- **seed_sources** — `id, source_id, source, variety, type, acquired_date, linked_plant_id, notes`
- **posts / post_images** — markdown blog posts with photo galleries
- **albums / album_images** — photo albums (uploads, URL imports, Immich imports)

Deleting a post, observation, or album cascades to its images and removes the
files from disk.

## Tests

```bash
pip install pytest httpx
pytest -q
```

Covers CRUD across every router, multi-image upload and static serving, cascade
file cleanup, non-image and traversal-filename rejection, validation bounds,
the stats aggregates, backup/restore round-trips, CSV import (preview + run,
idempotency, dedup), the digest builder, and the automatic DB column upgrade.
JS checks run separately — see `tests/test_photos.js`, `tests/test_import.js`,
`tests/test_day_modal.js`.

## Troubleshooting

### Immich import says "Imported 0 photos"
Your API key is almost certainly missing the **`asset.download`**
permission. Go to Immich → Account settings → API keys → edit your key and
tick `asset.download` (you need `album.read` and `asset.view` too). Verdant
now surfaces this directly in the import toast instead of failing silently.

### Immich section doesn't appear in the UI
Set `IMMICH_BASE_URL` and `IMMICH_API_KEY` in your `.env` (copy from
`.env.example`), then `docker compose up -d` again. If Verdant runs in Docker
on the same machine as Immich, use `http://host.docker.internal:2283` — not a
bare LAN IP — so the container can reach back to your host.

### Old database, new version: tabs error after upgrading
Fixed in v2.4.1+: Verdant adds missing columns automatically on startup, so
databases from v1.x upgrade cleanly. If you're on an older image, just pull
the latest.

### Changes not taking effect after editing compose/.env
`docker compose down && docker compose up -d` — containers don't pick up env
changes on a plain restart. Then hard-refresh the browser (Ctrl+F5).

### The digest never arrives
Check `DIGEST_ENABLED=true` is set (it's off by default), the webhook URL is
correct, and the container's clock/timezone matches yours — `DIGEST_TIME` is
server local time. Test with `POST /api/digest/send`.

## Changelog

- **2.14.0** — Tunnel-ready security, for the day Verdant meets the internet.
  Set `TUNNEL_MODE=true` and the app flips its secure preset: HSTS header on,
  `/docs` off, and the tunnel's proxy headers trusted. Always-on hardening
  underneath: security headers on every response, per-IP rate limiting on the
  API (1200/min, health checks exempt), and the container entrypoint honors
  `HOST`/`PORT`. `docker-compose.yml` ships a commented-out `cloudflared`
  service — pair it with a Cloudflare Access policy and there's no sign-on
  inside Verdant at all. Zero behavior change on plain LAN use.
- **2.13.0** — Measurement cleanup, so units finally mean what they say.
  Harvests carry a weight **unit** (oz/g/lb/kg) alongside the weight, and the
  yield **scorecard converts everything to ounces** — no more adding grams to
  ounces. The Review page leaderboard is now **split into two boards**: one
  ranked by weight, one by piece count, never mixed. CSV re-imports now
  **backfill weights** onto existing harvest rows, and watering/fertilization
  amounts are parsed into number + unit when they look like one
  (e.g. "2 gal"), with the original text always kept. New **°F/°C toggle** in
  Settings (weather chips honor it), planner vessels get a proper
  **volume (gal/qt/L)** instead of free-text size, and seed packets track
  **seed count**. Backups are now **optionally photo-less**: uncheck the box
  on the Backup page for a small database-only zip (restoring one leaves
  your current photos untouched). (To backfill your existing harvests,
  re-upload the harvest CSV on the Import page after updating.)
- **2.12.0** — New **🌱 Seedlings** tab: the indoor seed-starting workstation.
  Track every batch from sow to transplant — tray, location, warming mat,
  grow light, cells sown — with one-tap sprout logging, germination progress
  bars (including days-to-sprout), a stage pipeline (sowing → germinating →
  growing → hardening → transplanted), and a stale-batch nudge if nothing
  sprouts after 3 weeks. Finished batches keep their stats so next year's
  setup repeats what worked. Batches can link to a stash packet.
- **2.11.0** — Seed stash: packets now hold a **back-of-packet photo** too, for
  all the growing info printed on the reverse — a ⇄ flip button on the card
  swaps front/back (lightbox follows along). Also, **logo placeholders** are in
  place in the header, footer, and favicon: drop the real logo file into
  `app/static/img/logo-placeholder.svg` and it appears everywhere.
- **2.10.1** — Seed stash follow-up: the packet vendor is now a plain text
  field with autocomplete (each vendor listed once — no more repeats), and a
  **📦 Move sources to stash** button copies every seed source into the stash
  as a packet, pulling the vendor link and year out of the imported notes.
- **2.10.0** — The backyard update. **🗺️ Backyard Planner**: lay out grow
  bags, raised beds, pots and planters on a drag-and-drop canvas per season,
  assign plants to containers, copy last season's layout forward. **🏷️ NFC
  Tags**: `/t/<code>` tap links with a tag manager page — stick tags on
  fertilizer bottles, spray bottles, the harvest basket, the seed binder, or
  plant containers and land on exactly the right pre-filled screen; taps are
  counted. **🌱 Seed stash**: a real seed-packet catalog (photo, vendor link,
  type, year bought, quantity) as a second tab on the Seeds page. **🧪
  Fertilizers** finally gets a management page (name, NPK, best-for); the
  Garden Logs feeding form suggests from the shelf. **⚖️ Season scorecard**
  on the Review page: yield vs. spending per variety, ranked — expenses can
  now be tied to a plant on the Costs page.
- **2.9.0** — Immich album dedup: re-importing an album reuses the existing
  Verdant album instead of duplicating it, and **🧹 Merge duplicates** folds
  older double-imports into one (deleting the re-downloaded duplicate files).
  New **🎯 Match photos** page: flip through imported photos one by one and
  assign each to a plant (arrow-key navigation, bulk-assign a whole day's
  photos at once) — assigned photos appear in a gallery on the plant's
  profile. XMP sidecar keywords from Immich are captured as photo tags on
  import, backfilled for existing imports via the **🔄 Sync metadata** button.
- **2.8.0** — Settings page: pick your USDA hardiness zone once and Verdant
  derives your frost dates; morning digest controls (webhook, time, enabled)
  moved out of env vars into the UI.
- **2.7.0** — Tidy-up: interface cleanups and polish across the app.
- **2.6.0** — Full-screen `/slideshow` page with date/camera EXIF captions
  and 3/5/10/30s intervals; yield leaderboard on the Review page; `/quick`
  mobile quick-log (one-tap watering, harvest +/− stepper, "Water all" per
  location); expense tracking with per-category breakdown; seed-starting
  calendar on the Plants page tuned to your last frost date; pest treatment
  log.
- **2.5.1** — NULL-handling fixes: pre-existing rows with NULL camera/source
  fields no longer 500 the Photos tab; CSV import copes with legacy NOT NULL
  constraints in old databases.
- **2.5.0** — CSV import: bring your own data from another garden tracker.
  Upload → preview (counts, warnings, sample rows) → import, for locations,
  plants, fertilizers, seed sources, watering, fertilization, and harvests.
  Idempotent: your exported IDs are preserved and re-runs skip instead of
  duplicating. New `/import` page in the nav.
- **2.4.2** — Immich import failures are surfaced instead of swallowed: the
  toast names the cause, and a 403 on photo download tells you to tick
  `asset.download` on your API key. Fully-failing batches stop early.
- **2.4.1** — Automatic database column sync on startup (old v1.x databases
  upgrade cleanly, no manual migrations) and Immich v3 album-asset fetching.
  Batched Immich imports: the 200-photo cap is gone — albums import 50 photos
  per request with an `Importing… n/total` progress readout, idempotent so
  retries never duplicate.
- **2.4.0** — Seed Sources tab: vendor-grouped cards, vendor filter,
  add/edit/delete, and linking sources to plants.
- **2.3.0** — Morning garden digest via Discord webhook (overdue / due today /
  coming up), with preview and send-now endpoints for testing.
- **2.2.0** — Backup & restore: full database + uploads as a zip download,
  new `/backup` page in the nav.
- **2.1.0** — Garden core: plant profiles with care cadence and reminders,
  harvest tracking, per-plant timelines and timelapse, season review page,
  Open-Meteo weather auto-stamp on observations.
- **2.0.0** — Multi-page app (blog, observations, calendar as standalone
  routes), v2 data model: plants, locations, fertilizers, seed sources,
  harvests, watering logs.
- **1.3.x** — Calendar heatmap fixes; Immich integration (browse + import
  server albums); security hardening (Immich secrets via env only).
- **1.1.0** — Albums: create/upload/URL-import photo collections; "Pull from
  album" picker; version shown in UI + API.
- **1.0.0** — Initial release: posts, fertilization + observation logs,
  multi-image uploads, Docker.

---

*Built for one garden, shared with anyone who wants their own. If you grow
something worth bragging about, the blog tab is right there.*
