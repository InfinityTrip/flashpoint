from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from flashpoint import queries
from flashpoint.api.filters import Filters

router = APIRouter()

# Grid cell size in degrees for each zoom level: coarse when the whole globe is in view.
CELL_SIZES = [(1.5, 4.0), (2.5, 2.0), (3.5, 1.0), (4.5, 0.5)]
FINEST_CELL = 0.25


def cell_size_for_zoom(zoom: float) -> float:
    for max_zoom, size in CELL_SIZES:
        if zoom < max_zoom:
            return size
    return FINEST_CELL


def parse_bbox(value: str | None) -> queries.BBox | None:
    if value is None:
        return None
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be four numbers: west,south,east,north") from None
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(
            422, "bbox is out of range: longitudes -180..180, latitudes -90..90, south < north"
        )
    return queries.BBox(west, south, east, north)


class CellProperties(BaseModel):
    count: int
    top_type: int  # most common CAMEO root code in the cell


class PointGeometry(BaseModel):
    type: str = "Point"
    coordinates: tuple[float, float]  # [lon, lat]


class CellFeature(BaseModel):
    type: str = "Feature"
    geometry: PointGeometry
    properties: CellProperties


class GridResponse(BaseModel):
    type: str = "FeatureCollection"
    cell_size: float
    total: int
    features: list[CellFeature]


@router.get(
    "/events/grid",
    response_model=GridResponse,
    summary="Event counts per grid cell, for zoomed-out map views",
)
def events_grid(
    request: Request,
    zoom: Annotated[float, Query(ge=0, le=24, description="Map zoom level; sets the cell size")],
    filters: Filters,
    bbox: Annotated[
        str | None, Query(description="west,south,east,north in degrees; omit for the whole world")
    ] = None,
) -> GridResponse:
    cell_size = cell_size_for_zoom(zoom)
    with request.app.state.engine.connect() as conn:
        cells = queries.grid_counts(conn, cell_size, parse_bbox(bbox), filters)
    return GridResponse(
        cell_size=cell_size,
        total=sum(cell["count"] for cell in cells),
        features=[
            CellFeature(
                geometry=PointGeometry(coordinates=(cell["lon"], cell["lat"])),
                properties=CellProperties(count=cell["count"], top_type=cell["top_type"]),
            )
            for cell in cells
        ],
    )


class PointProperties(BaseModel):
    id: int  # GDELT's GlobalEventID; GET /v1/events/{id} returns the full event
    root_code: int
    date_added: datetime


class PointFeature(BaseModel):
    type: str = "Feature"
    geometry: PointGeometry
    properties: PointProperties


class PointsResponse(BaseModel):
    type: str = "FeatureCollection"
    truncated: bool  # true when more events matched than `limit`; only the newest are returned
    features: list[PointFeature]


@router.get(
    "/events",
    response_model=PointsResponse,
    summary="Individual events at city or province precision, newest first",
)
def events_points(
    request: Request,
    filters: Filters,
    bbox: Annotated[
        str | None, Query(description="west,south,east,north in degrees; omit for the whole world")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=5000, description="Most events to return")] = 2000,
) -> PointsResponse:
    with request.app.state.engine.connect() as conn:
        rows, truncated = queries.event_points(conn, parse_bbox(bbox), filters, limit)
    return PointsResponse(
        truncated=truncated,
        features=[
            PointFeature(
                geometry=PointGeometry(coordinates=(row["lon"], row["lat"])),
                properties=PointProperties(
                    id=row["id"], root_code=row["root_code"], date_added=row["date_added"]
                ),
            )
            for row in rows
        ],
    )


# GDELT's ActionGeo_Type, grouped into the three precisions the detail card shows.
PRECISION = {1: "country", 2: "province", 3: "city", 4: "city", 5: "province"}


class ConflictType(BaseModel):
    root_code: int
    name: str
    colour: str


class Actor(BaseModel):
    name: str | None
    country_code: str | None  # CAMEO (ISO 3166 alpha-3) code, e.g. SDN
    country_name: str | None


class Place(BaseModel):
    name: str | None
    geo_type: int
    precision: Literal["country", "province", "city"]
    country_code: str | None  # FIPS 10-4 code, e.g. SU
    country_name: str | None
    region_id: str | None
    region_name: str | None
    lon: float
    lat: float


class EventDetail(BaseModel):
    id: int
    date_added: datetime  # when GDELT recorded the report
    event_date: date  # when the event itself happened, as coded from the article
    conflict_type: ConflictType
    event_code: str
    action: str | None  # the CAMEO action in plain words; null if the code isn't in the lookup
    actor1: Actor
    actor2: Actor
    place: Place
    num_mentions: int | None
    num_sources: int | None
    num_articles: int | None
    goldstein: float | None  # -10 (most destabilising) to +10
    avg_tone: float | None  # average tone of the covering articles; negative is hostile
    source_url: str | None


def _actor(row: dict, n: int) -> Actor:
    return Actor(
        name=row[f"actor{n}_name"],
        country_code=row[f"actor{n}_country"],
        country_name=row[f"actor{n}_country_name"],
    )


@router.get(
    "/events/{event_id}",
    response_model=EventDetail,
    summary="Every stored field for one event",
    responses={404: {"description": "No such event, or it is older than the retention window"}},
)
def event_detail(request: Request, event_id: int) -> EventDetail:
    with request.app.state.engine.connect() as conn:
        row = queries.event_detail(conn, event_id)
    if row is None:
        raise HTTPException(404, f"no event {event_id}; events are kept for 35 days")
    return EventDetail(
        id=row["id"],
        date_added=row["date_added"],
        event_date=row["event_date"],
        conflict_type=ConflictType(
            root_code=row["root_code"], name=row["type_name"], colour=row["type_colour"]
        ),
        event_code=row["event_code"],
        action=row["action"],
        actor1=_actor(row, 1),
        actor2=_actor(row, 2),
        place=Place(
            name=row["place_name"],
            geo_type=row["geo_type"],
            precision=PRECISION[row["geo_type"]],
            country_code=row["country_code"],
            country_name=row["country_name"],
            region_id=row["region_id"],
            region_name=row["region_name"],
            lon=row["lon"],
            lat=row["lat"],
        ),
        num_mentions=row["num_mentions"],
        num_sources=row["num_sources"],
        num_articles=row["num_articles"],
        goldstein=row["goldstein"],
        avg_tone=row["avg_tone"],
        source_url=row["source_url"],
    )
