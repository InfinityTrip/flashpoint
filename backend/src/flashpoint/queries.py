"""Hand-written SQL, one function per API need."""

from dataclasses import dataclass

from sqlalchemy import Connection, text


def database_is_reachable(conn: Connection) -> bool:
    return conn.execute(text("SELECT 1")).scalar_one() == 1


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


def grid_counts(conn: Connection, cell_size: float, bbox: BBox | None) -> list[dict]:
    """Event counts per grid cell of `cell_size` degrees, with each cell's most common type.

    ST_SnapToGrid moves every point to the nearest multiple of cell_size, so all events in
    the same cell share one snapped point, which is also the cell's centre.
    """
    sql = f"""
        SELECT
            ST_X(cell) AS lon,
            ST_Y(cell) AS lat,
            count(*) AS count,
            mode() WITHIN GROUP (ORDER BY root_code) AS top_type
        FROM (
            SELECT ST_SnapToGrid(location, :cell_size) AS cell, root_code
            FROM events
            WHERE {_bbox_condition(bbox)}
        ) AS cells
        GROUP BY cell
        ORDER BY count DESC
    """
    params = {"cell_size": cell_size, **(bbox.__dict__ if bbox else {})}
    return [dict(row) for row in conn.execute(text(sql), params).mappings()]
