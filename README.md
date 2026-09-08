# 🌿 Verdant — Gardening Blog & Observation Log (v1.1.0)

Self-hosted garden journal: markdown blog posts with photo galleries, fertilization
records, and plant observation logs. FastAPI + SQLite + a single-page Tailwind
dashboard, all in one container.

## Stack

| Layer      | Choice                                            |
|------------|---------------------------------------------------|
| Backend    | FastAPI (Python 3.12), Uvicorn                     |
| Database   | SQLite via SQLModel (SQLAlchemy + Pydantic)        |
| Frontend   | Single HTML page, Tailwind CDN, vanilla JS (no build step) |
| Container  | Dockerfile + docker-compose with host volumes      |

Palette: **sage green**, **navy blue**, **beige** accents.

## Quick start (Docker — recommended)

```bash
docker-compose up --build
```

Open <http://localhost:8000>. Interactive API docs: <http://localhost:8000/docs>.

Change the host port with `GARDEN_PORT=9000 docker-compose up --build`.

### Persistence

`docker-compose.yml` bind-mounts two host directories, so nothing is lost on
rebuild or restart:

| Host path    | Container path | Contents                    |
|--------------|----------------|-----------------------------|
| `./data`     | `/data`        | `garden.db` (SQLite, WAL)   |
| `./uploads`  | `/uploads`     | Uploaded images             |

## Quick start (local, no Docker)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Layout

```
garden-log/
├── app/
│   ├── main.py           FastAPI app, static + /uploads mounts, SPA index
│   ├── database.py       engine, session dep, init_db (WAL, FK pragma)
│   ├── models.py         SQLModel tables
│   ├── schemas.py        request/response models
│   ├── storage.py        secure image save/delete
│   ├── routers/
│   │   ├── posts.py            blog CRUD + image upload
│   │   ├── fertilizations.py   fertilization CRUD
│   │   ├── observations.py     observation CRUD + image upload
│   │   └── stats.py            dashboard aggregates
│   └── static/           index.html, app.js, styles.css
├── tests/test_api.py     end-to-end API tests
├── Dockerfile
├── docker-compose.yml
├── data/                 SQLite volume (gitignored)
└── uploads/              image volume (gitignored)
```

## Data model

- **posts** — `id, title, content (markdown), created_at, updated_at`
- **post_images** — `id, post_id → posts.id, file_path, uploaded_at` (many per post)
- **fertilization_logs** — `id, date, fertilizer_name, npk_ratio, amount_used, notes`
- **observation_logs** — `id, date, plant_name, health_scale (1–10), watering_status (bool), pest_sightings, notes`
- **observation_images** — `id, observation_id → observation_logs.id, file_path, uploaded_at`

Deleting a post or observation cascades to its images and removes the files from disk.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET`    | `/api/posts?q=&limit=&offset=`     | List / search posts (newest first) |
| `POST`   | `/api/posts`                       | Create post (JSON) |
| `GET`    | `/api/posts/{id}`                  | Read post with images |
| `PATCH`  | `/api/posts/{id}`                  | Partial update (bumps `updated_at`) |
| `DELETE` | `/api/posts/{id}`                  | Delete post + images + files |
| `POST`   | `/api/posts/{id}/images`           | Upload 1..n images (multipart `files`) |
| `DELETE` | `/api/posts/{id}/images/{img_id}`  | Delete one image |
| `GET/POST` | `/api/fertilizations`            | List / create |
| `GET/PATCH/DELETE` | `/api/fertilizations/{id}` | Read / update / delete |
| `GET`    | `/api/observations?plant=`         | List, optional plant filter |
| `POST`   | `/api/observations`                | Create |
| `GET/PATCH/DELETE` | `/api/observations/{id}` | Read / update / delete |
| `POST`   | `/api/observations/{id}/images`    | Upload 1..n images |
| `DELETE` | `/api/observations/{id}/images/{img_id}` | Delete one image |
| `GET`    | `/api/stats`                       | Counts, average health, last watered |
| `GET`    | `/api/health`                      | Healthcheck |
| `GET`    | `/api/albums`                      | List albums with images |
| `POST`   | `/api/albums`                      | Create album (multipart `name`, optional `files`) |
| `GET`    | `/api/albums/{id}`                 | Read album with images |
| `DELETE` | `/api/albums/{id}`                 | Delete album + files |
| `POST`   | `/api/albums/{id}/import`          | Import URLs into album (`{"urls":[...]}`) |
| `POST`   | `/api/import/urls`                 | Import URLs into existing/new album |
| `POST`   | `/api/posts/{id}/from-album`       | Copy album images into a post (`{"album_id":n,"image_ids":[...]}`) |

Example:

```bash
# create a post and attach two photos
ID=$(curl -s -X POST localhost:8000/api/posts \
  -H 'Content-Type: application/json' \
  -d '{"title":"First tomatoes","content":"## Week 12\n\n**Brandywines** set fruit."}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

curl -s -X POST localhost:8000/api/posts/$ID/images \
  -F files=@bed1.jpg -F files=@bed2.jpg
```

## Upload security

- File type is decided by **magic bytes**, not by the client's filename or
  `Content-Type` (jpg, png, gif, webp, bmp only → otherwise `415`).
- Stored filenames are random hex, so a hostile filename cannot traverse
  directories or overwrite anything (`../../etc/passwd.png` becomes
  `/uploads/posts/3/<random>.png`).
- 8 MB cap per file, enforced while streaming; partial files are removed on failure.
- Deletes are confined to the uploads root by a resolved-path check.

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `GARDEN_DATA_DIR`     | `./data`    | Directory holding `garden.db` |
| `GARDEN_UPLOAD_DIR`   | `./uploads` | Image storage root |
| `GARDEN_DATABASE_URL` | `sqlite:///<data>/garden.db` | Full DB URL |
| `GARDEN_PORT`         | `8000`      | Host port (compose only) |
| `GARDEN_PUBLIC_URL`   | `http://localhost` | Base URL used to resolve relative URLs in "Import from URL" |

## Tests

```bash
pip install pytest httpx
pytest -q
```

Covers post/fertilization/observation CRUD, multi-image upload and static
serving, cascade file cleanup, non-image and traversal-filename rejection,
validation bounds, and the stats aggregate.

## Versioning

The version lives in one place: `app/version.py`. Bump it with every change
(minor for features, patch for fixes). It feeds:

- the `version` shown on the FastAPI app (visible at `/docs`)
- `GET /api/health` → `{"status":"ok","version":"1.1.0"}`
- the footer pill on every page (HTML `data-version` must match)
- the docker image tag in `docker-compose.yml`

Changelog:
- **1.1.0** — Albums: create/upload/URL-import photo collections; "Pull from
  album" picker on new entries; `GARDEN_PUBLIC_URL`; version shown in UI + API.
- **1.0.0** — Initial release: posts, fertilization + observation logs,
  multi-image uploads, stats, Docker.
