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
