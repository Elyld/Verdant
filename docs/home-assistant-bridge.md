# Home Assistant ↔ Verdant bridge

**Audience:** developers maintaining Verdant. This documents the contract Home Assistant depends on,
so Verdant can change without silently breaking the HA side.

Live since 2026-10-01/02. Every fact here was observed against a running instance — request/response
shapes, validation behaviour, error strings — rather than inferred from the schema. Where something is
an assumption rather than an observation, it says so.

Environment-specific values (host paths, addresses, ports) are intentionally generalized in this file,
since the repo is public. The HA-side consumer config is the authoritative source for those.

---

## 1. Topology

Home Assistant runs as a Docker container in its own network; Verdant runs as a separate container.
They do not share a Docker network, so HA reaches Verdant through the Docker Desktop gateway hostname
**`host.docker.internal`**. Use that form rather than a LAN IP: LAN addresses are typically
DHCP-assigned and the gateway form works regardless.

Consequence: **Verdant never needs to know HA's address for the read path.** HA is the only side that
initiates reads. HA's writes use the same gateway hostname.

**Verdant's API is intentionally unauthenticated** — it is designed for trusted-LAN/home use. The
bridge relies on that. Adding auth to the existing endpoints would break every HA sensor
simultaneously (see §5), so coordinate first if that changes.

---

## 2. Direction A — Home Assistant reads Verdant

| Endpoint | Poll interval | Consumed fields |
|---|---|---|
| `GET /api/today` | 300s | `date`, `due[]`, `harvest_forecast[]`, `frost.*`, `watering_advice.line` |
| `GET /api/plants/reminders/list` | 300s | `kind`, `status` (filtered) |
| `GET /api/stats` | 600s | `avg_health`, `last_watered`, `posts`, `fertilizations`, `observations`, `images` |
| `GET /api/stats/scorecard` | 3600s | `year`, `varieties[].variety`, `varieties[].total_qty` |
| `GET /api/plants/` | 3600s | array length only (plant count) |

Derived HA entities: crops ready to harvest, tasks due today, days until first frost (plus
`frost_date` and `source` as attributes), watering advice, average plant health, last watered,
journal-entry totals, harvests this year, plant count, and plants needing water / feed.

### Field-level semantics HA assumes

**`harvest_forecast[].status`** — HA counts `status == "ready"` as ready-to-harvest and lists
`status == "growing"` separately. Both values observed. Treat this string as part of the public API;
renaming either value silently zeroes the dashboard.

**`harvest_forecast[].plant_name`** — surfaced verbatim in a dashboard list.

**`frost`** — HA uses `days_until` (integer), `first_frost_date` (`YYYY-MM-DD`) and `source`.
`days_until` must be computed from the *current local date*; see §4 for why.

**`watering_advice.line`** — rendered directly into a dashboard card, so it is user-facing prose.
Unicode and emoji are fine.

**`/api/plants/reminders/list`** — HA counts rows where `kind == "water"` (resp. `"feed"`) **and**
`status` is in `["due", "overdue"]`.

The full status vocabulary, confirmed from `app/schemas.py`:

| `status` | Meaning |
|---|---|
| `unset` | No cadence configured for this plant — nothing to schedule |
| `overdue` | Past due, or cadence set but never watered |
| `due` | Due today |
| `soon` | Due within 2 days |
| `ok` | Not due |

So HA's `due`/`overdue` filter is correct as written.

⚠️ **HA currently ignores `soon`.** That is a gap worth closing on the HA side: `soon` is the
predictive value, and surfacing it would let HA warn *before* a plant is due rather than only when
it is already late. Not a Verdant issue — noted here so the vocabulary has a documented consumer
story for every value.

⚠️ **Because all plants currently report `unset`, the HA "plants needing water/feed" sensors read 0
permanently.** They are correct, not broken. They will start reporting once per-plant watering and
feeding cadences are configured in Verdant. Anyone debugging the bridge should check cadences before
suspecting the integration.

**`/api/stats.last_watered`** — nullable; HA renders `null` as "never logged". Prefer `null` over an
empty string if that phrasing is wanted.

**`/api/stats/scorecard`** — HA sums `total_qty` across `varieties[]` and lists the variety names.
`total_qty` must stay numeric, not a string, or the sum breaks.

---

## 3. Direction B — Home Assistant writes to Verdant

### `POST /api/watering-logs/`

**The schema and the API disagree, and this is the one known defect in the contract.**

The OpenAPI `requestBody` marks only `date` as required, but sending `date` alone returns:

```
400 {"detail":"Watering needs a location: pass location_id or use a plant that has one."}
```

HA therefore sends `location_id` (chosen from a dropdown of all ten locations) plus `date`, `method`
and `notes`. The business rule is sound — a watering should attach to something — but the contract
does not express it, so a client written against the schema fails at runtime with a business-rule
error instead of a validation error.

**Recommended fix (Verdant side):** keep the rule, express it. Either document the precondition
explicitly, or return `422` with field-level detail so clients can surface it as a validation failure.
Two further considerations:

- The endpoint also accepts `plant_id`; a plant with an associated location satisfies the rule. So the
  precondition is really "one of `location_id`, or a `plant_id` that resolves to a location".
- If global (location-less) waterings should be legal, that is a product decision — but it should be
  an explicit opt-in rather than inferred from omitted fields.
- **HA's location dropdown hard-codes the current ten location IDs.** If locations are added or
  reordered, that goes stale. A `GET /api/locations/`-driven selector on the HA side would be more
  robust; worth doing on the HA side if location churn is expected.

Returns the created row with numeric `id` and a `watering_id` (`WATER-XXXXXXXX`).

### `POST /api/observations`

- Required: `date`, `plant_name`. HA sends `health_scale` (int 1–10) and `notes`.
- The response **auto-fills** `temp_c` and `weather_summary` from Verdant's weather lookup (observed:
  `temp_c: 16.8`, `weather_summary: "Partly cloudy"`). Good feature — HA relies on it and does not
  send weather itself.
- Path has **no trailing slash**: `POST /api/observations` works; `/api/observations/` is not
  registered. Filtering reuses the same path with query params (`?limit=`, `?plant=`, `?date_from=`,
  `?date_to=`).

### `POST /api/harvests/`

- Required: `plant_id`, `date`, `quantity`. HA sends `unit` and `notes`.
- Returns numeric `id` plus `harvest_id` (`HARV-XXXXXXXX`).

### Cleanup contract

`DELETE /api/watering-logs/{id}`, `DELETE /api/observations/{id}` and `DELETE /api/harvests/{id}` all
return **204** and accept the numeric `id` from the POST response. This is what makes non-destructive
integration testing possible — please keep 204 + numeric-id semantics stable.

### Error bodies

`400` with a `{"detail": "..."}` body is what HA surfaces to the user. Human-readable details (like
the watering message above) are genuinely useful for debugging the bridge; prefer them over generic
messages when the cause is a business rule rather than a type error.

---

## 4. Deployment note: the timezone trap

**Set `TZ` on the Verdant container.** It previously had none, so the container ran UTC while the host
and Home Assistant ran local time. After 19:00 local, `/api/today` reported *tomorrow's* date.

Symptoms this caused downstream:

1. A row written by HA appeared "missing" when queried on the date HA displayed — it was filed on the
   other day. Query both candidate dates before concluding a write failed.
2. A dashboard header showed one date while same-evening journal entries carried another.
3. The frost countdown was off by one: Verdant computed 17 days from its UTC "tomorrow" while the
   correct local answer was 18.

**Consequences for Verdant development:**

- Anything computing "today" server-side (`/api/today`, reminder due-dates, `days_until`, watering
  advice) uses local time now. If UTC semantics are wanted internally, that should be explicit.
- The API emits bare `YYYY-MM-DD` with no zone, so **a consumer cannot tell which zone a date is in.**
  This is the root cause of the class of bug above. Recommended: emit ISO-8601 with an offset, or
  document the zone in the API contract, so the bridge never depends on container configuration again.
- `GET /api/stats/frost` and the `frost` block of `/api/today` are date-delta computations and are the
  highest-risk spots for this bug class.
- **The live container's compose file is not in this repo.** The `docker-compose.yml` here defines a
  *different* instance of the app; editing it will not affect the deployment the bridge talks to.
  This is worth knowing before debugging "but I changed the compose file".

---

## 5. Changes that would silently break Home Assistant

Ranked by how quietly they fail:

1. **Renaming `harvest_forecast[].status` values** (`ready` / `growing`) → crops-ready reads 0.
2. **Changing the reminder `status` vocabulary** (`due` / `overdue` / `soon` / `ok` / `unset`) → the
   plants-needing-water/feed sensors read 0 forever. Note `soon` is currently unused by HA (see §2).
3. **Adding auth to the existing endpoints** → every HA sensor goes `unavailable` at once.
4. **Changing response *shape*** (object → array, renaming a key, adding a nesting level) rather than
   a value → the REST sensors keep their **last known value** instead of erroring loudly.
   **Shapes fail soft; values fail loud.** Adding optional fields is safe. Renaming or nesting is not.
5. **Removing the container `TZ`, or reverting it** → off-by-one dates and the frost countdown
   regress (§4).
6. **Dropping the watering location precondition** or silently defaulting a location → HA's dropdown
   becomes meaningless without any visible error.
7. **Returning a non-numeric `total_qty`** → the scorecard sum renders as a template error.
8. **Turning `/api/plants/` into a paginated object** instead of a bare array → plant count reads 0.
   If pagination is needed, add a new endpoint rather than changing this one.

---

## 6. Verifying from the Verdant side (no HA knowledge needed)

```bash
# read path
curl -s localhost:<port>/api/today \
  | jq '{date, frost, ready: (.harvest_forecast | map(select(.status=="ready")) | length)}'
curl -s localhost:<port>/api/stats | jq
curl -s localhost:<port>/api/plants/reminders/list \
  | jq 'group_by(.kind) | map({kind: .[0].kind, statuses: (map(.status) | unique)})'

# write path, non-destructively (create, then delete)
R=$(curl -s -X POST localhost:<port>/api/watering-logs/ -H 'Content-Type: application/json' \
      -d '{"date":"2026-10-01","location_id":5,"notes":"integration test - delete me"}')
ID=$(echo "$R" | jq -r .id)
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE localhost:<port>/api/watering-logs/$ID  # expect 204
```

Confirm the container clock matches the host — this is the check that catches §4:

```bash
docker exec <container> date    # must print LOCAL time, not UTC
```

---

## 7. The HA-side consumer

The HA caller is a single YAML package: read sensors, write commands, and the three log-button
scripts all live in one file (`packages/verdant.yaml` inside the HA config directory). Read-side
entities are `sensor.verdant_*`; write-side scripts are `script.verdant_log_*`. If you need to know
exactly what a field is used for, that file is the definitive answer.

---

## 8. Change process

Agreed between the two sides:

- No renaming of JSON keys, no new auth on the existing endpoints, and no list→paginated-object
  changes without coordinating first.
- A change that would break the HA sensors is raised **before** it merges, not after.
- Shapes are the dangerous class (§5.4). Value changes are visible; shape changes are silent.

## 9. Open items on the HA side

- HA ignores the `soon` status (§2) — the predictive water/feed warning is not surfaced yet.
- HA's watering dropdown hard-codes the ten location IDs (§3) — fragile if locations change.
- No HA automation yet consumes garden data (e.g. frost warnings at 21/7/1 days); the sensors exist
  and are currently unused.
