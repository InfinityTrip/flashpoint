# Flashpoint architecture

Flashpoint is a public map of news-reported conflict events worldwide, built from the [GDELT 2.0](https://www.gdeltproject.org/) event feed. A scheduled job stores each new GDELT file in PostgreSQL + PostGIS. A FastAPI service answers filtered map queries over the last 35 days. A React frontend draws the results on a 3D globe.

Terms used here (event, conflict type, surge, baseline, replay, ingest run, retention window) are defined in [`GLOSSARY.md`](GLOSSARY.md).

## System overview

```
 GDELT 2.0 (zipped TSV every 15 min)
        │  httpx
        ▼
 ┌──────────────────┐      ┌───────────────────────────┐
 │ Ingest job       │─────▶│ PostgreSQL + PostGIS      │
 │ Railway cron     │      │ Neon                      │
 │ every 15 min     │      └─────────────▲─────────────┘
 └──────────────────┘                    │ SQL (SQLAlchemy Core)
                           ┌─────────────┴─────────────┐
                           │ FastAPI  /v1/             │
                           │ Railway, always on        │
                           └─────────────▲─────────────┘
                                         │ JSON / GeoJSON
                           ┌─────────────┴─────────────┐
                           │ React + MapLibre globe    │
                           │ Cloudflare Pages          │
                           └───────────────────────────┘
```

The ingest job and the API share one Python package (`backend/`) and one container image. The cron service runs the ingest command; the web service runs the API.

| Layer | Technology |
|---|---|
| Database | PostgreSQL + PostGIS on Neon (free tier, 1 GB) |
| Migrations | Alembic, raw SQL revisions |
| Data access | SQLAlchemy Core + psycopg 3, hand-written SQL, no ORM |
| API | FastAPI, Pydantic v2, uvicorn |
| Ingest | Python 3.13, httpx, stdlib `csv` |
| Frontend | Vite, React, TypeScript, MapLibre GL JS v5 (globe projection), TanStack Query, Tailwind |
| Basemap | CARTO Dark Matter |
| Hosting | Railway (API + cron), Cloudflare Pages (frontend), Neon (database) |
| Tooling | uv, ruff, pytest, ESLint, Vitest, Docker Compose, GitHub Actions |

## Ingest pipeline

GDELT publishes one zipped, tab-separated export every 15 minutes. File names follow a timestamp pattern, and `lastupdate.txt` names the newest one.

Each run of the ingest job:

1. Reads the newest available timestamp.
2. Lists every 15-minute timestamp after the last stored file, up to the newest.
3. For each timestamp, in order:
   - Download and unzip the file.
   - Keep rows with CAMEO root codes 14–20.
   - Insert the kept rows, skipping GDELT event ids that are already stored.
   - Record an ingest run.
   - All of this happens in one transaction per file.
4. Deletes events and ingest runs older than the 35-day retention window.
5. Exits.

Properties that fall out of this design:

- **Idempotent:** re-running a file inserts nothing new, because GDELT rows are append-only and unique by `GLOBALEVENTID`.
- **Self-healing:** missed or failed runs are picked up by the next run. A missing file (HTTP 404) is recorded as `skipped`; other errors are recorded as `failed` and retried.
- **One code path:** the initial 35-day backfill (about 3,400 files) is the same loop with a longer range.

## Data model

The data model is normalized: small lookup tables, plus one large, append-only, time-ordered `events` table.

```
regions (7 World Bank regions)
   ▲
countries (FIPS code PK, ISO code, name, region)
   ▲
events ──▶ event_types (CAMEO root 14–20, name, colour)
   ┊
   ┊ (looked up by full code, no foreign key)
   ▼
cameo_actions (full CAMEO code, plain-words description)

ingest_runs (one row per 15-minute file)
```

- **`events`** keeps about 20 of GDELT's 61 columns:
  - GDELT event id
  - date reported (`DATEADDED`) and the event's own date (`SQLDATE`)
  - CAMEO root and full code
  - Goldstein score, average tone, and mention, source and article counts
  - the two actors and their countries
  - location precision, place name, country, and a PostGIS point (SRID 4326)
  - source URL
- **`cameo_actions`** holds GDELT's description of each full CAMEO code under roots 14–20 (for example 193, "Fight with small arms and light weapons"). It has no foreign key from `events`, so an unknown code is still stored.
- **`countries`** maps GDELT's FIPS 10-4 codes to ISO codes, names and regions. Events whose code isn't in the table are stored with a null country.
- **Indexes:**
  - a GiST index on the point (map area queries)
  - B-tree on date reported (time windows and retention)
  - composite B-trees on (country, date reported) and (root code, date reported) (filters and surges)
- **`ingest_runs`** records each file's timestamp, status, row counts and error. It is the pipeline's audit log and drives `/v1/health`.

GDELT events are machine-coded from news articles. One real-world event often appears as several rows, and nothing is deduplicated, so the interface calls them "news-reported events". Only city- and province-precision events are drawn as points. Events placed at a country's centre point are still counted in grids and surges.

## API (`/v1/`)

Every map endpoint shares one filter vocabulary:

| Parameter | Meaning |
|---|---|
| `region` | World Bank region id |
| `country` | FIPS country code |
| `type` | one or more CAMEO root codes, 14–20 |
| `start`, `end` | ISO dates, applied to the date reported |

Relative windows count back from the newest stored data, so a stalled ingest never fakes a collapse.

| Endpoint | Returns |
|---|---|
| `GET /v1/events/grid?zoom&bbox` | Counts per grid cell (`ST_SnapToGrid`), with the cell size set by zoom |
| `GET /v1/events?bbox&limit` | Individual city- and province-precision events as GeoJSON, newest first, with a `truncated` flag |
| `GET /v1/events/{id}` | Every stored field for one event, with type, action, place and actor countries resolved |
| `GET /v1/surges?region&type` | Countries surging now, ranked by σ |
| `GET /v1/replay` | One coarse grid per day across the retention window |
| `GET /v1/filters` | Regions, countries, conflict types, available date range |
| `GET /v1/health` | Database status and minutes since the last successful ingest |

The API also has:

- interactive OpenAPI docs at `/docs`
- per-IP rate limiting (HTTP 429 with `Retry-After`)
- `Cache-Control: public, max-age=300` on map data
- CORS limited to the frontend's domain and localhost

## Surge detection

A surge is a country whose last 7 days are statistically unusual compared with its own baseline. One SQL statement computes it:

- **This week:** daily counts over the 7 complete UTC days ending at the newest complete day.
- **Baseline:** daily counts over the 21 days before that. Days with no events count as zero.
- **Score:** σ = (this week's daily mean − baseline mean) ÷ max(baseline standard deviation, 1).
- **Qualifies:** σ ≥ 2 and at least 25 events this week. Results are ranked by σ.

Each country is judged against its own normal variation, so a country that is always busy needs a larger jump to surge than a quiet one.

## Frontend

- **Globe:** MapLibre GL JS v5 with the globe projection and the CARTO Dark Matter basemap. When zoomed out it draws grid counts; when zoomed in, points coloured by conflict type.
- **View state:** filters and camera position live in the URL through one codec, so every view is a shareable link.
- **Panels:**
  - filter bar on top
  - "Surging now" on the left (a pull-up sheet on phones)
  - detail card on click
  - replay controls
  - "About this data"
  - a footer showing data freshness
- **Data fetching:** TanStack Query caches responses and keeps the previous data on screen while new data loads.

## Testing

- **Backend:** tests use a single seam. Synthetic GDELT export files go in through the ingest job, JSON comes out of the HTTP API, and a real PostGIS database sits in between, run with Docker Compose locally and as a service container in CI. Tests assert only on behaviour a client could observe.
- **Frontend:** unit tests cover the URL-state codec. Type checks and the production build run in CI.

## Running locally

Docker Compose starts PostGIS, the API and the frontend dev server together. Commands are defined in `backend/pyproject.toml`, `frontend/package.json` and the compose file.

## Build checklist

- [ ] Skeleton: local stack, globe, `/v1/health`, CI
- [ ] Ingest the newest GDELT file; grid counts on the globe
- [ ] Catch-up, 35-day backfill, retention, health freshness
- [ ] Filters and shareable URLs
- [ ] Points and event detail card
- [ ] Live deploy: Neon, Railway API and cron, Cloudflare Pages
- [ ] Surging now
- [ ] Replay
- [ ] API hardening: rate limits, cache headers, docs
- [ ] About panel, footer, mobile layout, README

## Later

- Historical episodes (curated replays from before the retention window)
- API keys, data export and alerts
