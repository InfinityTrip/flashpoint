"""Hand-written SQL, one function per API need."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text


def data_freshness(conn: Connection) -> dict:
    """The newest GDELT file stored successfully, and how many minutes ago it was published."""
    row = (
        conn.execute(
            text("""
            SELECT
                max(file_timestamp) AS latest_data_at,
                extract(epoch FROM now() - max(file_timestamp)) / 60 AS minutes_since_update
            FROM ingest_runs
            WHERE status = 'succeeded'
        """)
        )
        .mappings()
        .one()
    )
    minutes = row["minutes_since_update"]
    return {
        "latest_data_at": row["latest_data_at"],
        "minutes_since_update": None if minutes is None else float(minutes),
    }


@dataclass(frozen=True)
class BBox:
    """A lon/lat bounding box. west > east means it crosses the antimeridian (180°)."""

    west: float
    south: float
    east: float
    north: float


def _bbox_condition(bbox: BBox | None) -> str:
    """SQL condition limiting events to the box; uses the GiST index via the && operator."""
    if bbox is None:
        return "TRUE"
    if bbox.west <= bbox.east:
        return "location && ST_MakeEnvelope(:west, :south, :east, :north, 4326)"
    # Crossing the antimeridian: split into the part east of `west` and the part west of `east`.
    return """(
        location && ST_MakeEnvelope(:west, :south, 180, :north, 4326)
        OR location && ST_MakeEnvelope(-180, :south, :east, :north, 4326)
    )"""


@dataclass(frozen=True)
class EventFilters:
    """The shared filters every map endpoint accepts, already validated and resolved."""

    region: str | None = None  # World Bank region id
    country: str | None = None  # FIPS code
    types: tuple[int, ...] = ()  # CAMEO root codes; empty means all
    # Reported-time window (from, to]. GDELT's file stamped 00:00 holds the last 15 minutes of
    # the previous day, so an interval that excludes `from` puts that file on the right day.
    time_from: datetime | None = None
    time_to: datetime | None = None


def _filter_condition(filters: EventFilters) -> tuple[str, dict]:
    """SQL condition and parameters for the shared filters."""
    conditions, params = [], {}
    if filters.region:
        conditions.append(
            "country_code IN (SELECT fips_code FROM countries WHERE region_id = :region)"
        )
        params["region"] = filters.region
    if filters.country:
        conditions.append("country_code = :country")
        params["country"] = filters.country
    if filters.types:
        conditions.append("root_code = ANY(:types)")
        params["types"] = list(filters.types)
    if filters.time_from:
        conditions.append("date_added > :time_from")
        params["time_from"] = filters.time_from
    if filters.time_to:
        conditions.append("date_added <= :time_to")
        params["time_to"] = filters.time_to
    return " AND ".join(conditions) or "TRUE", params


def newest_event_time(conn: Connection) -> datetime | None:
    """When the most recently reported event was added; relative windows count back from it."""
    return conn.execute(text("SELECT max(date_added) FROM events")).scalar()


def lookup_codes(conn: Connection) -> dict[str, set[str]]:
    """Valid region ids and country codes, for validating filter parameters."""
    return {
        "regions": set(conn.execute(text("SELECT id FROM regions")).scalars()),
        "countries": set(conn.execute(text("SELECT fips_code FROM countries")).scalars()),
    }


def filter_vocabulary(conn: Connection) -> dict:
    """Everything a client needs to build filter controls."""
    regions = conn.execute(text("SELECT id, name FROM regions ORDER BY name")).mappings().all()
    types = conn.execute(
        text("SELECT root_code, name, colour FROM event_types ORDER BY root_code")
    ).mappings()
    # Only countries that have events, busiest first, so dropdowns aren't padded with empties.
    countries = conn.execute(
        text("""
            SELECT c.fips_code, c.name, c.region_id, count(*) AS event_count
            FROM events e
            JOIN countries c ON c.fips_code = e.country_code
            GROUP BY c.fips_code, c.name, c.region_id
            ORDER BY event_count DESC, c.name
        """)
    ).mappings()
    first, last = conn.execute(text("SELECT min(date_added), max(date_added) FROM events")).one()
    return {
        "regions": [dict(r) for r in regions],
        "countries": [dict(c) for c in countries],
        "conflict_types": [dict(t) for t in types],
        "date_range": {"first": first, "last": last},
    }


def grid_counts(
    conn: Connection, cell_size: float, bbox: BBox | None, filters: EventFilters
) -> list[dict]:
    """Event counts per grid cell of `cell_size` degrees, with each cell's most common type.

    ST_SnapToGrid moves every point to the nearest multiple of cell_size, so all events in
    the same cell share one snapped point, which is also the cell's centre.
    """
    where, filter_params = _filter_condition(filters)
    sql = f"""
        SELECT
            ST_X(cell) AS lon,
            ST_Y(cell) AS lat,
            count(*) AS count,
            mode() WITHIN GROUP (ORDER BY root_code) AS top_type
        FROM (
            SELECT ST_SnapToGrid(location, :cell_size) AS cell, root_code
            FROM events
            WHERE {_bbox_condition(bbox)} AND {where}
        ) AS cells
        GROUP BY cell
        ORDER BY count DESC
    """
    params = {"cell_size": cell_size, **(bbox.__dict__ if bbox else {}), **filter_params}
    return [dict(row) for row in conn.execute(text(sql), params).mappings()]


# GDELT location types precise enough to draw as a point: 2 US state, 3 US city, 4 world city,
# 5 world province. Type 1 is a whole country, placed at its centre, which would make every
# country's centre look like a hotspot.
POINT_GEO_TYPES = (2, 3, 4, 5)


def event_points(
    conn: Connection, bbox: BBox | None, filters: EventFilters, limit: int
) -> tuple[list[dict], bool]:
    """The most-reported city- and province-precision events, and whether more matched.

    When a view holds more events than `limit`, the ones kept are those covered by the most
    articles (GDELT's NumArticles), newest first among equals.
    """
    where, filter_params = _filter_condition(filters)
    # Asking for one row more than the limit tells us whether anything was cut off,
    # without a separate count(*) over every matching event.
    sql = f"""
        SELECT
            global_event_id AS id,
            ST_X(location) AS lon,
            ST_Y(location) AS lat,
            root_code,
            date_added
        FROM events
        WHERE geo_type IN {POINT_GEO_TYPES} AND {_bbox_condition(bbox)} AND {where}
        ORDER BY num_articles DESC NULLS LAST, date_added DESC, global_event_id DESC
        LIMIT :limit_plus_one
    """
    params = {"limit_plus_one": limit + 1, **(bbox.__dict__ if bbox else {}), **filter_params}
    rows = [dict(row) for row in conn.execute(text(sql), params).mappings()]
    return rows[:limit], len(rows) > limit


def event_detail(conn: Connection, event_id: int) -> dict | None:
    """One event with its conflict type, CAMEO action, place and actor countries resolved."""
    row = (
        conn.execute(
            text("""
            SELECT
                e.global_event_id AS id,
                e.date_added,
                e.event_date,
                e.root_code,
                t.name AS type_name,
                t.colour AS type_colour,
                e.event_code,
                a.description AS action,
                e.actor1_name,
                e.actor1_country,
                e.actor2_name,
                e.actor2_country,
                -- Actors use CAMEO country codes, which are ISO 3166 alpha-3. A code shared by
                -- several FIPS entries (PSE: Gaza Strip and West Bank) is ambiguous, so it
                -- gets no name rather than the wrong one.
                (SELECT min(name) FROM countries WHERE iso3 = e.actor1_country
                 HAVING count(*) = 1) AS actor1_country_name,
                (SELECT min(name) FROM countries WHERE iso3 = e.actor2_country
                 HAVING count(*) = 1) AS actor2_country_name,
                e.place_name,
                e.geo_type,
                e.country_code,
                c.name AS country_name,
                r.id AS region_id,
                r.name AS region_name,
                ST_X(e.location) AS lon,
                ST_Y(e.location) AS lat,
                e.num_mentions,
                e.num_sources,
                e.num_articles,
                e.goldstein,
                e.avg_tone,
                e.source_url
            FROM events e
            JOIN event_types t ON t.root_code = e.root_code
            LEFT JOIN cameo_actions a ON a.event_code = e.event_code
            LEFT JOIN countries c ON c.fips_code = e.country_code
            LEFT JOIN regions r ON r.id = c.region_id
            WHERE e.global_event_id = :event_id
        """),
            {"event_id": event_id},
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)
