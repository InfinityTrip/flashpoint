"""The `scope=major` filter: violent, internationally reported events, one point per article."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from flashpoint.ingest import run_ingest
from tests.gdelt_fixtures import FakeGdelt, gdelt_row

T0 = datetime(2026, 10, 18, 9, 15, tzinfo=UTC)


def grid_total(client: TestClient, **params) -> int:
    response = client.get("/v1/events/grid", params={"zoom": 1, **params})
    assert response.status_code == 200, response.text
    return response.json()["total"]


def point_ids(client: TestClient, **params) -> list[int]:
    response = client.get("/v1/events", params=params)
    assert response.status_code == 200, response.text
    return sorted(f["properties"]["id"] for f in response.json()["features"])


def test_major_scope_keeps_violent_events_reported_by_several_sources(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(
        T0,
        [
            gdelt_row(event_id=1, event_code="193", root_code=19, url="https://a.example/1"),
            gdelt_row(event_id=2, event_code="145", root_code=14, url="https://a.example/2"),
            gdelt_row(event_id=3, event_code="1451", root_code=14, url="https://a.example/3"),
            gdelt_row(event_id=4, event_code="175", root_code=17, url="https://a.example/4"),
            gdelt_row(event_id=5, event_code="186", root_code=18, url="https://a.example/5"),
            gdelt_row(event_id=6, event_code="202", root_code=20, url="https://a.example/6"),
            # Left out: a peaceful protest, an arrest, and fighting reported by one source only.
            gdelt_row(
                event_id=7, event_code="141", root_code=14, sources=9, url="https://a.example/7"
            ),
            gdelt_row(event_id=8, event_code="173", root_code=17, url="https://a.example/8"),
            gdelt_row(
                event_id=9, event_code="193", root_code=19, sources=1, url="https://a.example/9"
            ),
        ],
    )
    run_ingest(engine, gdelt.source())

    assert point_ids(client, scope="major") == [1, 2, 3, 4, 5, 6]
    assert grid_total(client, scope="major") == 6
    assert grid_total(client, scope="all") == 9
    assert grid_total(client) == 9  # the API's default scope is every event


def test_major_points_show_one_event_per_source_article(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    # One article often yields several coded events; the most-reported one stands for it.
    story = "https://news.example/story"
    gdelt.publish(
        T0,
        [
            gdelt_row(event_id=1, url=story, articles=3),
            gdelt_row(event_id=2, url=story, articles=12),
            gdelt_row(event_id=3, url=story, articles=5, place="Omdurman, Khartoum, Sudan"),
            gdelt_row(event_id=4, url="https://news.example/other"),
        ],
    )
    run_ingest(engine, gdelt.source())

    assert point_ids(client, scope="major") == [2, 4]
    assert point_ids(client, scope="all") == [1, 2, 3, 4]


def test_unknown_scope_is_rejected(client: TestClient) -> None:
    assert client.get("/v1/events", params={"scope": "important"}).status_code == 422
