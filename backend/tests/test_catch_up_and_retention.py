from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, text

from flashpoint.ingest import run_ingest
from tests.gdelt_fixtures import FakeGdelt, gdelt_row

T0 = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
Q = timedelta(minutes=15)


def at(n: int) -> datetime:
    """The n-th 15-minute GDELT file after T0."""
    return T0 + n * Q


def event_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM events")).scalar_one()


def run_statuses(engine: Engine) -> dict[datetime, str]:
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT file_timestamp, status FROM ingest_runs")).all())


def test_missed_files_are_caught_up_in_order(engine: Engine, gdelt: FakeGdelt) -> None:
    gdelt.publish(at(0), [gdelt_row(added=at(0))])
    run_ingest(engine, gdelt.source())
    for n in (1, 2, 3):
        gdelt.publish(at(n), [gdelt_row(added=at(n)), gdelt_row(added=at(n))])

    results = run_ingest(engine, gdelt.source())

    assert [(r.file_timestamp, r.status) for r in results] == [
        (at(1), "succeeded"),
        (at(2), "succeeded"),
        (at(3), "succeeded"),
    ]
    assert event_count(engine) == 7


def test_a_missing_file_is_skipped_and_later_files_still_load(
    engine: Engine, gdelt: FakeGdelt
) -> None:
    gdelt.publish(at(0), [gdelt_row(added=at(0))])
    run_ingest(engine, gdelt.source())
    gdelt.publish(at(2), [gdelt_row(added=at(2))])  # GDELT never published at(1)

    results = run_ingest(engine, gdelt.source())

    assert [(r.file_timestamp, r.status) for r in results] == [
        (at(1), "skipped"),
        (at(2), "succeeded"),
    ]
    # A skipped file is final: the next run doesn't ask for it again.
    assert run_ingest(engine, gdelt.source()) == []


def test_a_failed_file_is_retried_on_the_next_run(engine: Engine, gdelt: FakeGdelt) -> None:
    gdelt.publish(at(0), [gdelt_row(added=at(0))])
    run_ingest(engine, gdelt.source())
    gdelt.publish(at(1), [gdelt_row(added=at(1))])
    gdelt.publish(at(2), [gdelt_row(added=at(2))])
    gdelt.broken.add("20261018091500")  # at(1) answers HTTP 500

    first = run_ingest(engine, gdelt.source())

    assert [(r.file_timestamp, r.status) for r in first] == [
        (at(1), "failed"),
        (at(2), "succeeded"),
    ]
    assert "HTTPStatusError" in first[0].error

    gdelt.broken.clear()
    second = run_ingest(engine, gdelt.source())

    assert [(r.file_timestamp, r.status) for r in second] == [(at(1), "succeeded")]
    assert run_statuses(engine)[at(1)] == "succeeded"
    assert event_count(engine) == 3


def test_first_normal_run_on_an_empty_database_loads_only_the_newest_file(
    engine: Engine, gdelt: FakeGdelt
) -> None:
    gdelt.publish(at(0), [gdelt_row(added=at(0))])
    gdelt.publish(at(4), [gdelt_row(added=at(4))])

    results = run_ingest(engine, gdelt.source())

    assert [r.file_timestamp for r in results] == [at(4)]


def test_backfill_loads_every_file_in_the_retention_window(
    engine: Engine, gdelt: FakeGdelt
) -> None:
    latest = at(0)
    in_window = [latest - 10 * Q, latest - 50 * Q, latest - 95 * Q]
    too_old = latest - 96 * Q  # exactly one day before latest: outside a 1-day window
    for ts in [latest, *in_window, too_old]:
        gdelt.publish(ts, [gdelt_row(added=ts)])

    results = run_ingest(engine, gdelt.source(), backfill=True, retention_days=1)

    assert len(results) == 96  # every 15-minute slot in the day up to and including latest
    succeeded = sorted(r.file_timestamp for r in results if r.status == "succeeded")
    assert succeeded == sorted([latest, *in_window])
    assert sum(r.status == "skipped" for r in results) == 92
    assert event_count(engine) == 4

    # Running the backfill again finds nothing left to do.
    assert run_ingest(engine, gdelt.source(), backfill=True, retention_days=1) == []


def test_retention_deletes_events_and_runs_older_than_the_window(
    engine: Engine, gdelt: FakeGdelt
) -> None:
    gdelt.publish(at(0), [gdelt_row(event_id=1, added=at(0) - timedelta(days=2))])
    run_ingest(engine, gdelt.source(), retention_days=1)
    later = at(0) + timedelta(days=1, minutes=30)
    gdelt.publish(
        later,
        [
            gdelt_row(event_id=2, added=later - timedelta(hours=25)),  # past the 1-day window
            gdelt_row(event_id=3, added=later - timedelta(hours=1)),
            gdelt_row(event_id=4, added=later),
        ],
    )

    run_ingest(engine, gdelt.source(), retention_days=1)

    with engine.connect() as conn:
        remaining = conn.execute(text("SELECT global_event_id FROM events")).scalars().all()
    assert sorted(remaining) == [3, 4]
    assert all(ts > later - timedelta(days=1) for ts in run_statuses(engine))
