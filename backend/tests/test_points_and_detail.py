from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from flashpoint.ingest import run_ingest
from tests.gdelt_fixtures import FakeGdelt, gdelt_row

T0 = datetime(2026, 10, 18, 9, 15, tzinfo=UTC)


def points(client: TestClient, **params) -> dict:
    response = client.get("/v1/events", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def point_ids(client: TestClient, **params) -> list[int]:
    return [f["properties"]["id"] for f in points(client, **params)["features"]]


def test_points_leave_out_country_precision_events(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(T0, [gdelt_row(event_id=i, geo_type=i) for i in (1, 2, 3, 4, 5)])
    run_ingest(engine, gdelt.source())

    assert sorted(point_ids(client)) == [2, 3, 4, 5]
    # The grid still counts every event, whatever its precision.
    assert client.get("/v1/events/grid", params={"zoom": 1}).json()["total"] == 5


def test_points_are_most_reported_first_then_newest(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(
        T0,
        [
            gdelt_row(event_id=1, articles=2, added=T0 - timedelta(hours=2)),
            gdelt_row(event_id=2, articles=2, added=T0),
            gdelt_row(event_id=3, articles=40, added=T0 - timedelta(hours=3)),
            gdelt_row(event_id=4, articles=9, added=T0 - timedelta(hours=1)),
        ],
    )
    run_ingest(engine, gdelt.source())

    assert point_ids(client) == [3, 4, 2, 1]


def test_points_are_truncated_at_the_limit(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(T0, [gdelt_row(event_id=i, articles=10 - i) for i in range(1, 6)])
    run_ingest(engine, gdelt.source())

    cut = points(client, limit=3)
    assert (len(cut["features"]), cut["truncated"]) == (3, True)
    assert [f["properties"]["id"] for f in cut["features"]] == [1, 2, 3]
    whole = points(client, limit=5)
    assert (len(whole["features"]), whole["truncated"]) == (5, False)


def test_points_limit_is_bounded(client: TestClient) -> None:
    assert client.get("/v1/events", params={"limit": 0}).status_code == 422
    assert client.get("/v1/events", params={"limit": 5001}).status_code == 422


def test_points_apply_the_filters_and_bbox(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    london = {"country": "UK", "place": "London, London, City of, United Kingdom"}
    gdelt.publish(
        T0,
        [
            gdelt_row(event_id=1, root_code=19),
            gdelt_row(event_id=2, root_code=14),
            gdelt_row(event_id=3, root_code=19, lat=51.5, lon=-0.12, **london),
            gdelt_row(event_id=4, root_code=19, added=T0 - timedelta(days=3)),
        ],
    )
    run_ingest(engine, gdelt.source())

    assert sorted(point_ids(client, country="SU")) == [1, 2, 4]
    assert sorted(point_ids(client, type=19)) == [1, 3, 4]
    assert sorted(point_ids(client, window="24h")) == [1, 2, 3]
    assert point_ids(client, bbox="-10,40,10,60") == [3]
    assert point_ids(client, region="SSF", type=14) == [2]


def test_point_features_carry_location_type_and_time(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(T0, [gdelt_row(event_id=9, root_code=18)])
    run_ingest(engine, gdelt.source())

    [feature] = points(client)["features"]
    assert feature == {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [32.5, 15.5]},
        "properties": {"id": 9, "root_code": 18, "date_added": "2026-10-18T09:15:00Z"},
    }


def test_event_detail_returns_every_field(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(T0, [gdelt_row(event_id=42, event_code="193", event_date="20261017")])
    run_ingest(engine, gdelt.source())

    response = client.get("/v1/events/42")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": 42,
        "date_added": "2026-10-18T09:15:00Z",
        "event_date": "2026-10-17",
        "conflict_type": {"root_code": 19, "name": "Fight", "colour": "#dc2626"},
        "event_code": "193",
        "action": "Fight with small arms and light weapons",
        "actor1": {"name": "SUDAN", "country_code": "SDN", "country_name": "Sudan"},
        "actor2": {"name": "RAPID SUPPORT FORCES", "country_code": "SDN", "country_name": "Sudan"},
        "place": {
            "name": "Khartoum, Khartoum, Sudan",
            "geo_type": 4,
            "precision": "city",
            "country_code": "SU",
            "country_name": "Sudan",
            "region_id": "SSF",
            "region_name": "Sub-Saharan Africa",
            "lon": 32.5,
            "lat": 15.5,
        },
        "num_mentions": 6,
        "num_sources": 2,
        "num_articles": 6,
        "goldstein": -10.0,
        "avg_tone": -8.5,
        "source_url": "https://example.com/news/article",
    }


def test_event_detail_falls_back_when_a_code_is_not_in_the_lookups(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(T0, [gdelt_row(event_id=43, event_code="1999", country="OS", geo_type=1)])
    run_ingest(engine, gdelt.source())

    event = client.get("/v1/events/43").json()

    assert event["action"] is None
    assert event["place"]["precision"] == "country"
    assert (event["place"]["country_name"], event["place"]["region_name"]) == (None, None)


def test_unknown_event_id_is_404(client: TestClient) -> None:
    response = client.get("/v1/events/999")

    assert response.status_code == 404
    assert "999" in response.json()["detail"]
