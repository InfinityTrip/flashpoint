"""The shared filter parameters (region, country, type, window or date range) and /v1/filters."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from flashpoint import queries

router = APIRouter()

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


def _lookups(request: Request) -> dict[str, set[str]]:
    # Region and country codes never change at runtime, so load them once per process.
    if not hasattr(request.app.state, "lookups"):
        with request.app.state.engine.connect() as conn:
            request.app.state.lookups = queries.lookup_codes(conn)
    return request.app.state.lookups


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def event_filters(
    request: Request,
    region: Annotated[str | None, Query(description="World Bank region id, e.g. SSF")] = None,
    country: Annotated[
        str | None, Query(description="GDELT FIPS country code, e.g. SU for Sudan")
    ] = None,
    type: Annotated[
        list[int] | None,
        Query(description="CAMEO root code 14-20; repeat for several (type=18&type=19)"),
    ] = None,
    window: Annotated[
        Literal["24h", "7d", "30d"],
        Query(description="Time before the newest event; ignored when start or end is given"),
    ] = "7d",
    start: Annotated[date | None, Query(description="First day reported (UTC), inclusive")] = None,
    end: Annotated[date | None, Query(description="Last day reported (UTC), inclusive")] = None,
    scope: Annotated[
        Literal["all", "major"],
        Query(
            description="major: only violent events (assault, fighting, mass violence, violent "
            "protest or repression) reported by at least 2 sources; points then show one event "
            "per source article"
        ),
    ] = "all",
) -> queries.EventFilters:
    """Validate the shared filters and resolve the time window to exact timestamps."""
    lookups = _lookups(request)
    if region is not None and region not in lookups["regions"]:
        raise HTTPException(422, f"unknown region {region!r}; see /v1/filters")
    if country is not None and country not in lookups["countries"]:
        raise HTTPException(422, f"unknown country {country!r}; see /v1/filters")
    types = tuple(sorted(set(type or [])))
    if any(not 14 <= t <= 20 for t in types):
        raise HTTPException(422, "type must be a CAMEO root code from 14 to 20")

    if start is not None or end is not None:
        if start is not None and end is not None and end < start:
            raise HTTPException(422, "end must not be before start")
        time_from = _day_start(start) if start else None
        time_to = _day_start(end + timedelta(days=1)) if end else None
    else:
        with request.app.state.engine.connect() as conn:
            newest = queries.newest_event_time(conn)
        time_from = newest - WINDOWS[window] if newest else None
        time_to = newest

    return queries.EventFilters(region, country, types, time_from, time_to, scope == "major")


# Endpoints declare `filters: Filters` to accept and validate the shared filter parameters.
Filters = Annotated[queries.EventFilters, Depends(event_filters)]


class Region(BaseModel):
    id: str
    name: str


class Country(BaseModel):
    fips_code: str
    name: str
    region_id: str | None
    event_count: int


class ConflictType(BaseModel):
    root_code: int
    name: str
    colour: str


class DateRange(BaseModel):
    first: datetime | None
    last: datetime | None


class FiltersResponse(BaseModel):
    regions: list[Region]
    countries: list[Country]
    conflict_types: list[ConflictType]
    date_range: DateRange


@router.get(
    "/filters",
    response_model=FiltersResponse,
    summary="Regions, countries, conflict types and the stored date range, for filter controls",
)
def filters(request: Request) -> FiltersResponse:
    with request.app.state.engine.connect() as conn:
        return FiltersResponse(**queries.filter_vocabulary(conn))
