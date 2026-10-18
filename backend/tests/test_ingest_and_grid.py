from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from flashpoint.ingest import run_ingest
from tests.gdelt_fixtures import FakeGdelt, gdelt_row

T0 = datetime(2026, 10, 18, 9, 15, tzinfo=UTC)


def grid(client: TestClient, **params) -> dict:
    response = client.get("/v1/events/grid", params={"zoom": 1, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_ingest_keeps_only_conflict_types(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    rows = [gdelt_row(root_code=code) for code in (1, 4, 10, 13, 14, 17, 19, 20)]
    gdelt.publish(T0, rows)

    [run] = run_ingest(engine, gdelt.source())

    assert (run.status, run.rows_read, run.rows_kept, run.rows_inserted) == ("succeeded", 8, 4, 4)
    assert grid(client)["total"] == 4


def test_ingest_rejects_rows_without_a_usable_location(engine: Engine, gdelt: FakeGdelt) -> None:
    gdelt.publish(
        T0,
        [gdelt_row(), gdelt_row(lat="", lon=""), gdelt_row(geo_type=0), gdelt_row(lat=95)],
    )

    [run] = run_ingest(engine, gdelt.source())

    assert run.rows_kept == 1


def test_reingesting_a_file_adds_nothing(engine: Engine, gdelt: FakeGdelt) -> None:
    gdelt.publish(T0, [gdelt_row(event_id=1), gdelt_row(event_id=2)])
    run_ingest(engine, gdelt.source())
    with engine.begin() as conn:  # forget the run so the same file is fetched again
        conn.execute(text("TRUNCATE ingest_runs"))

    [again] = run_ingest(engine, gdelt.source())

    assert (again.status, again.rows_kept, again.rows_inserted) == ("succeeded", 2, 0)


def test_newest_file_already_stored_is_not_fetched_again(engine: Engine, gdelt: FakeGdelt) -> None:
    gdelt.publish(T0, [gdelt_row()])
    run_ingest(engine, gdelt.source())

    assert run_ingest(engine, gdelt.source()) == []


def test_unknown_country_codes_are_stored_without_a_country(
    engine: Engine, gdelt: FakeGdelt
) -> None:
    gdelt.publish(T0, [gdelt_row(event_id=7, country="OS"), gdelt_row(event_id=8, country="SU")])

    run_ingest(engine, gdelt.source())

    with engine.connect() as conn:
        stored = dict(conn.execute(text("SELECT global_event_id, country_code FROM events")).all())
    assert stored == {7: None, 8: "SU"}


def test_each_run_is_recorded(engine: Engine, gdelt: FakeGdelt) -> None:
    gdelt.publish(T0, [gdelt_row(), gdelt_row(root_code=1)])

    run_ingest(engine, gdelt.source())

    with engine.connect() as conn:
        run = conn.execute(text("SELECT * FROM ingest_runs")).mappings().one()
    assert run["file_timestamp"] == T0
    assert (run["status"], run["rows_read"], run["rows_kept"], run["rows_inserted"]) == (
        "succeeded",
        2,
        1,
        1,
    )


def test_stored_event_keeps_gdelt_fields(engine: Engine, gdelt: FakeGdelt) -> None:
    gdelt.publish(
        T0, [gdelt_row(event_id=42, root_code=18, event_code="183", event_date="20261001")]
    )

    run_ingest(engine, gdelt.source())

    with engine.connect() as conn:
        event = (
            conn.execute(text("SELECT *, ST_X(location) AS lon, ST_Y(location) AS lat FROM events"))
            .mappings()
            .one()
        )
    assert event["root_code"] == 18
    assert event["event_code"] == "183"
    assert event["date_added"] == T0
    assert str(event["event_date"]) == "2026-10-01"
    assert (event["lon"], event["lat"]) == (32.5, 15.5)
    assert event["actor2_name"] == "RAPID SUPPORT FORCES"
    assert event["source_url"] == "https://example.com/news/article"


def test_grid_groups_events_into_cells_with_their_most_common_type(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(
        T0,
        [
            gdelt_row(lat=15.6, lon=32.6, root_code=19),
            gdelt_row(lat=15.4, lon=32.4, root_code=19),
            gdelt_row(lat=15.5, lon=32.5, root_code=14),
            gdelt_row(lat=50.4, lon=30.5, root_code=18, country="UP"),
        ],
    )
    run_ingest(engine, gdelt.source())

    body = grid(client, zoom=1)  # 4-degree cells

    assert body["type"] == "FeatureCollection"
    assert body["cell_size"] == 4.0
    assert body["total"] == 4
    cells = {tuple(f["geometry"]["coordinates"]): f["properties"] for f in body["features"]}
    assert cells == {
        (32.0, 16.0): {"count": 3, "top_type": 19},
        (32.0, 52.0): {"count": 1, "top_type": 18},
    }


def test_zooming_in_makes_cells_smaller(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(T0, [gdelt_row(lat=15.1, lon=32.1), gdelt_row(lat=15.9, lon=32.9)])
    run_ingest(engine, gdelt.source())

    assert len(grid(client, zoom=1)["features"]) == 1
    fine = grid(client, zoom=6)
    assert fine["cell_size"] == 0.25
    assert len(fine["features"]) == 2
    assert fine["total"] == 2


def test_bbox_limits_the_grid_to_the_visible_area(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    gdelt.publish(
        T0,
        [
            gdelt_row(lat=15.5, lon=32.5),  # Sudan
            gdelt_row(lat=50.4, lon=30.5, country="UP"),  # Ukraine
            gdelt_row(lat=-17.7, lon=178.4, country="FJ"),  # Fiji, just west of 180°
            gdelt_row(lat=-14.3, lon=-170.7, country="AQ"),  # American Samoa, just east of it
        ],
    )
    run_ingest(engine, gdelt.source())

    assert grid(client, bbox="20,0,45,30")["total"] == 1
    assert grid(client, bbox="170,-30,-160,0")["total"] == 2  # crosses the antimeridian


def test_grid_rejects_a_malformed_bbox(client: TestClient) -> None:
    for bad in ("1,2,3", "a,b,c,d", "0,10,10,5", "0,0,200,10"):
        response = client.get("/v1/events/grid", params={"zoom": 1, "bbox": bad})
        assert response.status_code == 422, bad
