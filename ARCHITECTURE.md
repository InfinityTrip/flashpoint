# Flashpoint — Architecture

> This document describes a system that does not exist yet. It's a design proposal/roadmap to build toward and revise as you learn, not a spec of finished code.

## 1. What this is, and why it's a *different* project from the MUN simulator

If you're also working on a MUN crisis/GA simulator, that project is fundamentally about **pushing live state to many connected people instantly** — WebSockets, session/room management, server-authoritative real-time state. Flashpoint is the opposite kind of problem on purpose: there's no "instant" requirement here. ACLED and GDELT aren't pushing data to you — they're APIs you **pull** from on their own schedule (GDELT refreshes roughly every 15 minutes; ACLED more like daily/weekly). A user filtering a map by region/date/conflict-type is querying **stored history**, not watching something happen live.

So Flashpoint is a **pull-based, request/response system**: a scheduled job periodically fetches and normalizes external data, and a REST API answers filtered queries against what's already stored. The skills this teaches — data pipelines, schema design for analytical workloads, geospatial querying, performance at scale — are deliberately distinct from the simulator's real-time/WebSocket focus.

---

## 2. This is an ETL pipeline, not just an API

**ETL** = **E**xtract (pull from ACLED/GDELT) → **T**ransform (normalize, dedupe, standardize dates/regions/categories) → **L**oad (write to Postgres). This needs to run **independently of the API server**, on a schedule — not triggered by an incoming user request.

- In Python, use a scheduler library like **APScheduler** running as its own process, or a hosted cron job (Railway and Render both support scheduled jobs) that runs a script every N minutes.
- Keep ingestion and query-serving as separate concerns in the codebase even if they end up deployed together at first — one path writes data, a different path reads it. Don't let a slow/failing ACLED API call block someone's map query.

**Idempotency matters.** Every ingestion run will re-encounter events it already has (especially since GDELT/ACLED update existing records, not just add new ones). Every incoming record needs a stable external ID (both APIs provide their own), and ingestion should use an **upsert** — Postgres's `INSERT ... ON CONFLICT (external_id) DO UPDATE ...` — keyed on that ID. Without this, every ingestion run duplicates data.

---

## 3. Schema design: star schema, not full normalization

Full normalization (a table per distinct concept, foreign keys everywhere) is the textbook default for transactional systems, and it's reasonable here for small lookup tables: `regions`, `conflict_types`, `sources`. But the big, ever-growing table — the actual events — should follow a **star schema**, a standard data-warehousing pattern used for analytical/read-heavy workloads:

```
        ┌───────────────┐        ┌───────────────────┐
        │   regions      │        │  conflict_types    │
        │  (dimension)   │        │   (dimension)       │
        └───────┬────────┘        └──────────┬──────────┘
                │                             │
                └──────────────┬──────────────┘
                                ▼
                       ┌─────────────────┐          ┌─────────────┐
                       │     events        │─────────▶│  sources     │
                       │  (fact table)      │          │ (dimension)  │
                       │  timestamp, lat/lon,│          └─────────────┘
                       │  casualties,        │
                       │  region_id (FK),     │
                       │  conflict_type_id(FK)│
                       │  source_id (FK),      │
                       │  external_id (unique) │
                       └─────────────────┘
```

One large **fact table** (`events`) holding the actual measurements/occurrences, referencing small **dimension tables** for categorical lookups. This biases toward fast filtered reads over strict normalization purity — the right tradeoff for a system built to be queried and filtered constantly, not transactionally updated.

---

## 4. Geospatial queries need a geospatial-aware database, not just lat/lon columns

Storing latitude/longitude as plain numbers works until you need real spatial queries — "events within this map viewport," "events inside this region's actual boundary" (not just a bounding box). Naive `WHERE lat BETWEEN ... AND lon BETWEEN ...` filtering doesn't scale and can't express real polygons.

**PostGIS** is a Postgres extension purpose-built for this: real geometry/geography types, and **spatial indexes** (a GiST index — optimized for "is this point inside this shape" and "what's near this point," the way a normal B-tree index is optimized for equality/range lookups on plain numbers). Worth adopting from the start rather than retrofitting once queries are already slow.

---

## 5. Volume is the real risk — plan for it before it's a problem

GDELT in particular is enormous — it tracks global events, not just conflict zones. Ingesting broadly rather than scoping to specific regions/conflict types from day one can grow the `events` table into the tens of millions of rows quickly, and naive queries will slow down fast. Two techniques to design in early:

- **Table partitioning** — Postgres can natively split one logical table into physical chunks by date range (e.g., one partition per month). A query filtering by date range only scans the relevant partitions instead of the whole table — a significant win for time-series data specifically.
- **Server-side aggregation for the map itself** — a user zoomed out on the world map can't usefully parse 50,000 individual points, and sending them all just to cluster client-side still means transferring everything. Instead, have the API return **pre-aggregated bins** (counts per grid cell or per region) at low zoom levels, and only return individual event points once someone zooms in far enough for the count to be reasonable. This is a backend design decision, not just a Leaflet rendering trick.

**Practical starting scope:** ingest a handful of specific regions/conflict types rather than "everything GDELT has," so you don't hit a volume wall before the frontend even exists. Broaden scope once the pipeline and schema are proven.

---

## 6. Caching

Underlying data changes at most every ~15 minutes (GDELT's refresh rate) — there's no reason to hit Postgres fresh for every identical filtered query from every visitor. A simple in-memory cache or Redis with a short TTL (e.g., cache a given filter combination's result for 5 minutes) meaningfully cuts load once more than a couple of people are using it. Not needed on day one — worth adding once there's real traffic to optimize for.

---

## 7. Recommended build order

1. **Schema first.** Design and migrate the star-schema tables (`events`, `regions`, `conflict_types`, `sources`) before writing any ingestion code — it's much easier to write a pipeline against a schema you've already committed to than to redesign both at once.
2. **One-off ingestion script.** A plain Python script that pulls a small, fixed date range from one API (start with whichever of ACLED/GDELT has simpler auth), transforms it, and upserts it into Postgres. No scheduler yet — just prove the pipeline works end to end, once, manually.
3. **Turn it into a scheduled job.** Wrap the script for APScheduler or a hosted cron trigger, running on an interval. Add idempotency checks if they weren't already airtight.
4. **FastAPI read endpoints.** `GET /events?region=&conflict_type=&start_date=&end_date=` with pagination — query the data you now have flowing in.
5. **PostGIS + spatial filtering.** Once basic filtering works, add real polygon/viewport-based geospatial queries.
6. **Leaflet frontend.** Map rendering, filters wired to the API, clustering/aggregation at low zoom levels.
7. **Partitioning + caching.** Add once data volume or traffic actually justifies it — not before.

---

## Possible future synergy with the MUN simulator (not a day-one concern)

MUN crisis committees simulate real geopolitical crises. Once Flashpoint has real, current conflict data flowing in, the simulator's AI-generated crisis updates could eventually pull from it to ground scenarios in what's actually happening in the world. Worth remembering, not worth designing for while both projects are still early — keep them decoupled until there's an actual reason to connect them.
