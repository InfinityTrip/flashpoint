from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from flashpoint import queries

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
    bbox: Annotated[
        str | None, Query(description="west,south,east,north in degrees; omit for the whole world")
    ] = None,
) -> GridResponse:
    cell_size = cell_size_for_zoom(zoom)
    with request.app.state.engine.connect() as conn:
        cells = queries.grid_counts(conn, cell_size, parse_bbox(bbox))
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
