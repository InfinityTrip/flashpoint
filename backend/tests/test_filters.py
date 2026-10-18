from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from flashpoint.ingest import run_ingest
from tests.gdelt_fixtures import FakeGdelt, gdelt_row

NEWEST = datetime(2026, 10, 18, 9, 15, tzinfo=UTC)


def total(client: TestClient, **params) -> int:
    response = client.get("/v1/events/grid", params={"zoom": 1, **params})
    assert response.status_code == 200, response.text
    return response.json()["total"]


@pytest.fixture
def world(engine: Engine, gdelt: FakeGdelt) -> None:
    """A small world of events, all reported in the newest GDELT file's 35-day window.

    Sudan (SU, Sub-Saharan Africa): fights now, 3 days ago and 10 days ago; a protest now.
    Ukraine (UP, Europe & Central Asia): an assault 2 hours ago.
    Israel (IS, Middle East & North Africa): a fight 20 days ago.
    """
    rows = [
        gdelt_row(country="SU", root_code=19, added=NEWEST),
        gdelt_row(country="SU", root_code=14, added=NEWEST),
        gdelt_row(country="SU", root_code=19, added=NEWEST - timedelta(days=3)),
        gdelt_row(country="SU", root_code=19, added=NEWEST - timedelta(days=10)),
        gdelt_row(
            country="UP", root_code=18, lat=50.4, lon=30.5, added=NEWEST - timedelta(hours=2)
        ),
        gdelt_row(
            country="IS", root_code=19, lat=31.5, lon=34.5, added=NEWEST - timedelta(days=20)
        ),
    ]
    gdelt.publish(NEWEST, rows)
    run_ingest(engine, gdelt.source())


@pytest.mark.usefixtures("world")
def test_default_window_is_the_7_days_before_the_newest_event(client: TestClient) -> None:
    assert total(client) == 4


@pytest.mark.usefixtures("world")
def test_relative_windows_count_back_from_the_newest_event(client: TestClient) -> None:
    assert total(client, window="24h") == 3
    assert total(client, window="7d") == 4
    assert total(client, window="30d") == 6


@pytest.mark.usefixtures("world")
def test_region_filter(client: TestClient) -> None:
    assert total(client, region="SSF", window="30d") == 4
    assert total(client, region="ECS", window="30d") == 1
    assert total(client, region="NAC", window="30d") == 0


@pytest.mark.usefixtures("world")
def test_country_filter(client: TestClient) -> None:
    assert total(client, country="SU", window="30d") == 4
    assert total(client, country="IS", window="30d") == 1


@pytest.mark.usefixtures("world")
def test_type_filter_accepts_several_types(client: TestClient) -> None:
    assert total(client, type=19, window="30d") == 4
    assert total(client, type=[14, 18], window="30d") == 2


@pytest.mark.usefixtures("world")
def test_date_range_covers_whole_days(client: TestClient) -> None:
    # 2026-10-08 holds the event from 10 days before NEWEST; 10-15 holds the one from 3 days before.
    assert total(client, start="2026-10-08", end="2026-10-08") == 1
    assert total(client, start="2026-10-08", end="2026-10-15") == 2
    assert total(client, start="2026-10-18", end="2026-10-18") == 3


@pytest.mark.usefixtures("world")
def test_a_date_range_overrides_the_window(client: TestClient) -> None:
    assert total(client, window="24h", start="2026-09-28", end="2026-09-28") == 1


@pytest.mark.usefixtures("world")
def test_filters_combine(client: TestClient) -> None:
    assert total(client, region="SSF", type=19, window="7d") == 2
    assert total(client, country="SU", type=14, window="24h") == 1


@pytest.mark.parametrize(
    "params",
    [
        {"region": "ATLANTIS"},
        {"country": "ZZ"},
        {"type": 13},
        {"type": 21},
        {"window": "2w"},
        {"start": "2026-10-10", "end": "2026-10-01"},
        {"start": "yesterday"},
    ],
)
def test_invalid_filters_are_rejected_with_422(client: TestClient, params: dict) -> None:
    response = client.get("/v1/events/grid", params={"zoom": 1, **params})

    assert response.status_code == 422, params
    assert "detail" in response.json()


@pytest.mark.usefixtures("world")
def test_filters_endpoint_lists_the_filter_vocabulary(client: TestClient) -> None:
    body = client.get("/v1/filters").json()

    assert {r["id"] for r in body["regions"]} == {"EAS", "ECS", "LCN", "MEA", "NAC", "SAS", "SSF"}
    assert [t["root_code"] for t in body["conflict_types"]] == [14, 15, 16, 17, 18, 19, 20]
    assert body["conflict_types"][5] == {"root_code": 19, "name": "Fight", "colour": "#dc2626"}
    # Only countries with stored events are listed, each under its region, busiest first.
    countries = {c["fips_code"]: c for c in body["countries"]}
    assert set(countries) == {"SU", "UP", "IS"}
    assert countries["SU"] == {
        "fips_code": "SU",
        "name": "Sudan",
        "region_id": "SSF",
        "event_count": 4,
    }
    assert body["date_range"] == {
        "first": "2026-09-28T09:15:00Z",
        "last": "2026-10-18T09:15:00Z",
    }


def test_filters_endpoint_works_before_any_data(client: TestClient) -> None:
    body = client.get("/v1/filters").json()

    assert body["countries"] == []
    assert body["date_range"] == {"first": None, "last": None}
