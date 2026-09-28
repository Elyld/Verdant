# 🌿 Verdant — Self-Hosted Garden Journal (v2.28.0)

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

### 🧭 Navigation — grouped tabs, custom mobile bar
The desktop nav is grouped into four labeled sections — **Grow** (Plants,
Seeds, Seedlings, Planner), **Track** (Garden Logs, Calendar, Quick Log,
Photos), **Manage** (Costs, Pests, Fertilizers, Review, Import, Tags), and
**Read** (Blog & Stories) — over a faint fern watermark, with no dropdown
menus anywhere. On your phone you get a bottom tab bar instead: pick up to
**4** of your own sections in the order you tap them, right on the
📱 *Mobile tab bar* card of the Settings page (tap a chip to add it, tap
again to remove — no dropdowns there either), and everything else stays one
tap away under **More**, which opens a bottom sheet of the remaining
sections. Out of the box the bar is Quick Log, Plants, Calendar, Planner.

![Mobile tab bar](docs/screenshots/nav-mobile.png)

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

### 📝 Garden Logs — the daily log
Log health (1–10), watering, pest sightings, and freeform notes per plant, per
day — with photos attached. Feedings live here too, with the feeding form
suggesting from your 🧪 Fertilizer shelf. New observations are automatically
stamped with the current weather at your garden (free Open-Meteo data, no API
key needed).

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

There's also a dedicated full-screen slideshow page — pick an album, pick an
interval, and let the garden scroll by on a TV or tablet.

![Full-screen slideshow](docs/screenshots/slideshow.png)

### 🌰 Seeds — sources & vendors
Track where every seed came from: vendors, trades, or saved seed. Grouped by
vendor, filterable, linkable to the plants you grew from them.

![Seed sources](docs/screenshots/seeds.png)

### 🌱 Seed stash — the binder, catalogued
Every packet you own, inventoried: a photo of the packet, vendor (with link),
type, year bought, and how many seeds are left. Searchable and filterable —
including a 📷 filter for which packs have photos. Packet photos can be
uploaded or picked straight from your photo library (e.g. an Immich album of
packet shots), and the ⇄ flip button shows the growing info on the back of
the packet. Stick an NFC tag on the binder and tapping it opens the
"add packet" form.

![Seed stash](docs/screenshots/seed-stash.png)

![Packet front/back flip](docs/screenshots/packet-flip.png)

![Pick a packet photo from the library](docs/screenshots/packet-library-picker.png)

### 🛒 Order assistant — winter seed ordering, minus the spreadsheet
Come ordering season, the **Order assistant** tab pulls it all together: every
stash packet with its age ("bought 2024 · 2 yrs old") and your one-tap
**grow again?** rating — 👎 Skip, 👍 Grow again, ⭐ Favorite (tap again to
clear) — plus last year's seed spend broken down by vendor, and a wishlist
where each variety shows the last vendor and date you ordered it (resolved
from your invoices). Tick the varieties you want and they roll up into an
order list per vendor. No new state to maintain: ratings live on the packets,
the wishlist is its own list, and invoices are the source of truth.

![Order assistant](docs/screenshots/order-assistant.png)

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
Lay out your actual growing space on a real grid (1 cell = 1 ft, resizable):
grow bags, raised beds, pots, planters, cattle panel arches, pallets — each
drawn at its true footprint, so a 4×8 bed actually looks 4×8 next to a 10-gal
bag. Drag containers and they snap to the grid (positions save automatically,
and you can't drop one on top of another). A container holds **many plants**
now — a bed lists everything in it — and the **🔁 rotation check** flags when
you put the same plant family where it grew last season. Copy last season's
layout into the new year and shuffle things around. Flip to the **3D view** to
walk your plan — orbit around the yard and see the beds, bags, arches, and
plants in space, which makes the layout click in a way a flat grid never does.
Click any container in 3D to edit it. A slim **🌤️ weather ribbon** runs under
the site header on every page — current conditions, tonight's low, tomorrow's
high, rain chance, and wind gusts. On the planner, **garden alerts** underneath
it read your actual data: frost warnings that name your tender containers, heat
alerts for the thirsty pots and bags, rain-skip nudges when you watered recently,
spray wash-off warnings, wind alerts for the arches, and a tomato blight watch.
Set your coordinates on the Settings page to light the ribbon up; until then it
stays quietly hidden. When the National Weather Service has active alerts for
your garden point, a severity-tinted ⚠️ pill appears in the ribbon — click it
for each alert's timing and details (free, no key; cached 15 minutes).

![Global weather ribbon](docs/screenshots/weather-ribbon.png)
Hit **🔥 Yield** to tint every container by last season's harvest weight
(darker = heavier), so the spots that earned their keep jump out. Open any
container and the **🌱 companion hints** suggest good and bad neighbors from a
curated, extension-service-sourced list.

![Backyard planner](docs/screenshots/planner.png)
![Backyard planner in 3D](docs/screenshots/planner-3d.png)
![Backyard planner with weather and yield heatmap](docs/screenshots/planner-heatmap.png)

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
one-tap watering per location ("Water all"), a harvest +/− stepper with an
optional **weight** input and unit (oz/g/lb/kg, prefilled from your default —
leave it blank and it's a plain count), and today's entries at a glance.
NFC tags can drop you straight here.

![Quick Log](docs/screenshots/quick.png)

### 💰 Costs — was it worth growing?
Every garden expense in one place, broken down by category — rows are
editable in place. Tag a purchase
to a plant and the Season Review scorecard splits costs per variety, so you
can finally answer whether the peppers beat the grocery store. Below the
expenses, a **🧾 Invoices** section keeps the paper trail: vendor, order
date, order number, total, and the PDF receipt, each optionally linked to
the expense it documents — and both invoices and expenses can be **tagged
with the seed packets** they bought (with smart suggestions matched from the
order text), so the Order assistant knows exactly what came from where.

![Costs](docs/screenshots/costs.png)

![Invoices](docs/screenshots/invoices.png)

### 🐛 Pests — the treatment log
What showed up, what you sprayed or squashed, and whether it worked — a
running log per pest so next year's battle plan writes itself.

![Pests](docs/screenshots/pests.png)

### 📥 CSV Import — bring your own data
Moving from another garden tracker? The **Import** page (nav bar → Import)
walks you through it: pick what you're importing (locations, plants,
fertilizers, seed sources, watering logs, fertilization logs, harvests, invoices),
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

### ⚙️ Settings — your garden's particulars
USDA zone, last/first frost dates (exact dates beat zone averages),
temperature units, which day your calendar week starts on, default harvest
weight unit, slideshow autoplay interval, and the morning digest schedule —
all on one page. Your **garden coordinates** live here too (with a
📍 *Use my location* button that fills them in from your browser, falling
back to a one-time city-level lookup) — they power the Planner's weather
strip and stamp new observations with the current conditions. The frost
dates drive the "days to first frost" countdown in the header and tune the
seed-starting calendar on the Plants page.

![Settings](docs/screenshots/settings.png)

### 🌅 Morning Digest — Discord
An optional daily "morning garden check" sent to a Discord channel via webhook:
what's overdue, what's due today, what's coming up. Off by default — set
`DIGEST_ENABLED=true` and `DISCORD_WEBHOOK_URL` to turn it on.

### 🔌 Immich integration
Browse albums on your own Immich server and import their photos straight into
Verdant — no downloading and re-uploading. Needs `IMMICH_BASE_URL` and
`IMMICH_API_KEY` (see [Configuration](#configuration)).

## Tips & tricks

A few workflows that aren't obvious until you've lived in the app a while:

- **NFC-tag everything you touch.** A tag on the fertilizer bottle opens the
  feeding form with that product pre-selected; one on the seed binder opens
  "add packet"; one per grow bag opens that plant's profile. Write the tag's
  URL once with any NFC writer app — no app needed to read them.
- **Quick Log belongs on your phone's home screen.** It's built for dirty
  hands: one-tap watering per location, a harvest stepper, and it works fine
  as a home-screen bookmark over your LAN.
- **Match photos with the keyboard.** On the 🎯 Match photos page, `←`/`→`
  flip through photos and number keys pick the plant — a 600-photo album goes
  fast. Bulk-assign a whole day when you know what it is.
- **Merge duplicates after an Immich import.** If an old import ran twice,
  🧹 Merge duplicates folds the copies into the fullest album instead of you
  deleting things by hand.
- **Tag costs to a plant.** The Season scorecard can only split spending per
  variety if purchases are tagged — do it at entry time and the year-end
  "was it worth growing?" math is free.
- **Photograph the back of the packet too.** The growing info on the reverse
  is the part you actually need in April; the ⇄ flip button keeps both sides
  on the packet card.
- **Copy the season in the planner.** January: copy last season's layout,
  drag things to their new spots, and the rotation check tells you where you
  planted the same family last year.
- **CSV imports are re-runnable.** The importer skips rows it already has
  (exported IDs are preserved), so re-importing a fixed file never creates
  duplicates. Import in the suggested order: locations → plants → the rest.
- **Database-only backups are fast.** Uncheck the photos box for a small zip
  you can grab before every upgrade; keep a full one with photos somewhere
  safe monthly.

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
| `GARDEN_LAT` / `GARDEN_LON` | (unset) | Fallback for your garden's coordinates — prefer the Settings page (📍 Use my location button). Stamps new observations with current weather + powers the site-wide weather ribbon (free Open-Meteo data, no key needed) |
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

Set your garden coordinates on the **Settings page** (preferred — there's a
📍 *Use my location* button that fills them in from your browser, falling back
to a one-time city-level lookup via ip-api.com when you click it) or with the
`GARDEN_LAT` / `GARDEN_LON` env vars (kept as a fallback; Settings win). Find
coordinates by hand by clicking your spot on the map at
<https://open-meteo.com>. Every new observation is then stamped with the
temperature and conditions at log time, and the Planner shows its weather
strip. Free, no API key.

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
| Invoices | `vendor`, `order_number`, `order_date`, `total`, `items`, `notes` |

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

- **2.29.0** — **⚠️ National Weather Service alerts in the ribbon.** The
  site-wide weather ribbon now shows a severity-tinted ⚠️ pill when the NWS
  has active alerts for your garden point (Freeze Warning, Wind Advisory,
  …) — click it to expand a panel with each alert's timing and details.
  Free, no key (api.weather.gov), cached 15 minutes server-side, and it
  degrades silently: no pill when there are no alerts, coords unset, or the
  service is unreachable. Needs garden coordinates set (Settings page), like
  the rest of the ribbon.
  ![NWS alert pill and panel](docs/screenshots/noaa-alerts.png)
- **2.28.0** — **🧭 Navigation refresh.** The desktop nav is now four labeled
  groups (Grow / Track / Manage / Read) with an icon on every tab and a faint
  fern watermark — no dropdown menus anywhere. On phones there's a bottom tab
  bar instead of the cramped top bar: it opens with Quick Log, Plants,
  Calendar, Planner + a fixed **More** tab, and you can make it yours on the
  new 📱 *Mobile tab bar* card in Settings — tap up to 4 section chips in the
  order you want them (tap again to remove; numbered 1–4), and the bar
  follows. More opens a bottom sheet with every other section, never
  duplicating your picks.
- **2.27.0** — **🌤️ The weather strip goes site-wide.** The forecast ribbon
  (current conditions, tonight's low, tomorrow's high, rain chance, wind gusts)
  now lives under the site header on **every** page instead of only the
  planner — slim, subtle, and rendered from the cached forecast endpoint, so
  it's cheap. It stays hidden until your garden coordinates are set (Settings
  page — no nagging), and the planner keeps its garden-alerts box, which reads
  your actual container data.
- **2.26.0** — **📍 Garden coordinates move to Settings.** Latitude/longitude
  are now first-class Settings-page fields (saved like everything else, no env
  vars needed) with a **Use my location** button: it tries your browser's
  geolocation first, and falls back to a one-time city-level IP lookup via
  ip-api.com — click-only, never in the background, nothing stored beyond the
  coordinates. Settings outrank the `GARDEN_LAT` / `GARDEN_LON` env vars (kept
  as fallback), so a stale env var can never shadow what you picked in the UI.
  The planner's unconfigured-weather hint now points at Settings too.
- **2.25.0** — **🛒 Winter seed-order assistant.** New tab on the Seeds page
  that pulls ordering season together: a ratings table for the stash (how old
  each packet is, one-tap "grow again?" ratings — 👎 Skip, 👍 Grow again,
  ⭐ Favorite — also editable from the packet form and shown as badges on the
  stash cards), last year's seed spend grouped by vendor from your invoices,
  and a winter wishlist. Each wishlist row shows the last vendor and date the
  variety was ordered (resolved from past invoices) and has a checkbox; ticked
  items roll up into an order list. Ratings are stored on the packet; the
  wishlist is its own list with add/edit/delete.
- **2.24.0** — **⚖️ Weight in Quick Log harvest.** The Quick Log harvest
  stepper now has a weight input + unit selector (prefilled from your
  Preferences, like the Plants page form), so the fastest way to log a
  harvest — including the NFC tap flow — captures the weight the scorecard's
  by-weight board and the yield heatmap need. Weight stays optional; logging
  by count alone works exactly as before. Also on the Planner page: when
  GARDEN_LAT/GARDEN_LON aren't set, the weather strip now shows a small
  dismissible hint explaining why instead of silently staying hidden.
- **2.23.0** — **🌱 Multi seed-packet tagging for invoices + expenses.** The
  invoice packet picker is now a true multi-select (checkbox panel — link as
  many packets as an order had), and the import preview links multiple packets
  per invoice too (strong suggestions pre-checked). Expenses ("transactions")
  get their own packet tagging: 🌱 chips with one-tap suggestions and the same
  multi picker on every expense row, backed by a new `expense_seed_packets`
  table. Invoice and expense tags are independent — tagging one never touches
  the other.
- **2.22.0** — **✏️ Expense editing + smarter invoice categories.** Expense
  rows on the Costs page now have edit and delete buttons — editing loads the
  row into the log-a-purchase form (Save changes / Cancel), and deleting an
  expense cleanly unlinks any invoices that pointed at it. Auto-created
  expenses are also categorized by vendor now (247Garden → Supplies, seed
  vendors → Seeds) with keyword fallback on the items text, instead of
  everything landing in Seeds.
- **2.21.0** — **💸 Expenses from invoices.** Creating an invoice now
  auto-creates its expense row (amount, date, vendor, items as notes) so the
  Costs page fills itself in — or link an existing expense by hand as before.
  Older invoices get a "➕ Create expense" button, edits to an invoice sync
  onto its auto-created expense, and deleting the invoice takes the
  auto-created expense with it. CSV imports back expenses automatically too,
  with re-runs still skipping cleanly.
- **2.20.0** — **🔗 Invoice ↔ seed packet links.** An invoice now knows which
  seed packets it bought: link packets from a picker on each invoice row, or
  tap a suggested match (the app guesses from the invoice's item text — you
  confirm). Links are shown as 🌱 chips and survive in backups; importing
  invoices from CSV offers the best-guess packet per row right in the preview.
- **Unreleased** — Fixed: the 🧾 Invoices section on the Costs page never
  rendered its table (a script variable was used before its declaration),
  so invoices now list correctly with PDF links and linked-expense badges.
  The README tour gains a dedicated Invoices screenshot.
- **2.19.0** — **🧾 Invoices** on the Costs page. Keep the paper trail for
  seed and supply orders: vendor, order date, order number, total, items,
  and the PDF receipt, each optionally linked to the expense it documents.
  Import them from CSV on the Import page (columns: `vendor`,
  `order_number`, `order_date`, `total`, `items`, `notes` — re-runs skip
  what's already there), and invoice PDFs ride along in backups.
- **2.18.0** — The visual refresh, plus a few fixes. Newsreader serif
  headings and Source Sans body text, a warmer beige palette, and the classic
  navy header. New ✨ Preferences card in Settings: which day the calendar
  week starts on, default harvest weight unit, slideshow autoplay interval,
  and a confirm-before-"Water all" guard for the Quick Log. The unguarded
  bulk-delete posts endpoint is gone (`DELETE /api/posts` now returns 405;
  deleting a single post still works). Fixed: `POST /api/plants/` no longer
  500s when `date_planted` arrives as an ISO string — dates are coerced,
  blanks become null, garbage gets a 422. Plus a pre-release audit pass over
  the backend and frontend fixing assorted small glitches. The README tour
  was re-shot in the new style with a new Tips & tricks section.
- **2.17.0** — Albums can now be deleted from the Photos page. Pick an album
  and hit **🗑️ Delete album**: a confirm dialog names the album and its photo
  count, then the album, its photo rows, and their downloaded files are all
  removed. Your originals in Immich are never touched, so re-importing is
  always an option; plant photo assignments from a deleted album are removed
  with it. Handy when duplicates or stale metadata make a clean re-import
  easier than surgery.
- **2.16.2** — Static assets (JS/CSS) now carry the app version in their URL,
  so browsers fetch fresh code after every redeploy instead of running stale
  cached scripts. Fixes the case where the footer showed a new version but
  page behavior was still the old build's.
- **2.16.1** — The photo-library picker now works when *adding* a packet too:
  pick a front/back photo on the add form and it's attached automatically when
  the packet is saved (a ✓ marks your pick until then). Previously the picker
  only appeared when editing an existing packet.
- **2.16.0** — Seed packets meet the photo library. A packet's front/back
  photo can now be picked from photos already in Verdant — e.g. an Immich
  album of packet shots — instead of only uploading a file. New
  `POST /api/seed-packets/{id}/photo-from-library` attaches a library photo
  as a *copy*, so the original album import is never touched. The seed stash
  gains a 📷 photo filter (all / with photos / without photos) for going
  through which packs have pictures so far.
- **2.15.0** — Planner 2.0: the backyard builder grows up. A real **grid
  system** (1 cell = 1 ft, resizable up to 60×60) with snap-to-grid dragging —
  containers are drawn at their **true footprint**, so a 4×8 raised bed dwarfs
  a 10-gal grow bag, and new containers land in the first free spot instead of
  piling up. Containers now hold **many plants** (a bed lists everything in
  it), and a **🔁 rotation check** warns when the same plant family goes back
  where it grew last season. New asset kinds: **cattle panel arches** (7 ft
  tall by default, height editable per container for the 3D view) and
  **pallets**. A **3D view** renders the whole plan in space — orbit around
  the yard, see every bed, bag, arch, and plant, click any of them to edit.
  Old free-form positions migrate to the grid automatically on first load.
  Then came the **intelligence batch**: a **🌤️ weather strip** (live conditions,
  tonight's low, tomorrow's high, rain chance, wind gusts — powered by
  Open-Meteo, set your coordinates in Settings), which went site-wide in
  v2.27.0 as a slim ribbon under the header on every page, plus **garden
  alerts** that read your actual data — frost warnings
  naming your tender containers, heat alerts for the thirsty pots, rain-skip
  nudges when you watered recently, spray wash-off warnings, wind alerts for
  the arches, and a tomato blight watch. The **🔥 Yield heatmap** tints every
  container by last season's harvest weight so you can see at a glance which
  spots earned their keep, and the **🌱 companion hints** in each container's
  modal suggest good (and bad) neighbors from a curated,
  extension-service-sourced list.
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
