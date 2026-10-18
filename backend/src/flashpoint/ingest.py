"""The ingest job: store GDELT's newest 15-minute export file, then exit.

Run by the Railway cron every 15 minutes: `python -m flashpoint.ingest`.
"""

import logging
import sys
from dataclasses import astuple, dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import Connection, Engine, text

from flashpoint.db import make_engine
from flashpoint.gdelt import GdeltSource, format_timestamp
from flashpoint.parser import Event, parse_row
from flashpoint.settings import get_settings

log = logging.getLogger("flashpoint.ingest")

# Same order as the fields of parser.Event.
STAGING_COLUMNS = (
    "global_event_id, date_added, event_date, root_code, event_code, goldstein,"
    " num_mentions, num_sources, num_articles, avg_tone, actor1_name, actor1_country,"
    " actor2_name, actor2_country, geo_type, place_name, country_code, lat, lon, source_url"
)


@dataclass(frozen=True)
class RunResult:
    file_timestamp: datetime
    status: str  # succeeded | skipped | failed
    rows_read: int | None = None
    rows_kept: int | None = None
    rows_inserted: int | None = None
    error: str | None = None


def store_events(conn: Connection, events: list[Event]) -> int:
    """Insert events, skipping ids already stored. Returns how many rows were new."""
    # Bulk-load into a scratch table with COPY (much faster than row-by-row INSERTs),
    # then move everything across in one INSERT that skips existing ids.
    conn.execute(
        text("""
            CREATE TEMP TABLE staging_events (
                global_event_id bigint, date_added timestamptz, event_date date,
                root_code smallint, event_code text, goldstein real,
                num_mentions integer, num_sources integer, num_articles integer,
                avg_tone real, actor1_name text, actor1_country text,
                actor2_name text, actor2_country text, geo_type smallint,
                place_name text, country_code text, lat double precision,
                lon double precision, source_url text
            ) ON COMMIT DROP
        """)
    )
    cursor = conn.connection.driver_connection.cursor()
    with cursor.copy(f"COPY staging_events ({STAGING_COLUMNS}) FROM STDIN") as copy:
        for event in events:
            copy.write_row(astuple(event))

    result = conn.execute(
        text("""
            INSERT INTO events (
                global_event_id, date_added, event_date, root_code, event_code, goldstein,
                num_mentions, num_sources, num_articles, avg_tone, actor1_name,
                actor1_country, actor2_name, actor2_country, geo_type, place_name,
                country_code, location, source_url
            )
            SELECT
                s.global_event_id, s.date_added, s.event_date, s.root_code, s.event_code,
                s.goldstein, s.num_mentions, s.num_sources, s.num_articles, s.avg_tone,
                s.actor1_name, s.actor1_country, s.actor2_name, s.actor2_country,
                s.geo_type, s.place_name,
                c.fips_code,  -- NULL when GDELT's country code isn't in our lookup table
                ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326),
                s.source_url
            FROM staging_events s
            LEFT JOIN countries c ON c.fips_code = s.country_code
            ON CONFLICT (global_event_id) DO NOTHING
        """)
    )
    return result.rowcount


def record_run(conn: Connection, run: RunResult, started_at: datetime) -> None:
    # A file that failed before is retried later; its row is overwritten with the new outcome.
    conn.execute(
        text("""
            INSERT INTO ingest_runs (
                file_timestamp, status, started_at, finished_at,
                rows_read, rows_kept, rows_inserted, error
            )
            VALUES (
                :file_timestamp, :status, :started_at, now(),
                :rows_read, :rows_kept, :rows_inserted, :error
            )
            ON CONFLICT (file_timestamp) DO UPDATE SET
                status = EXCLUDED.status,
                started_at = EXCLUDED.started_at,
                finished_at = EXCLUDED.finished_at,
                rows_read = EXCLUDED.rows_read,
                rows_kept = EXCLUDED.rows_kept,
                rows_inserted = EXCLUDED.rows_inserted,
                error = EXCLUDED.error
        """),
        {**run.__dict__, "started_at": started_at},
    )


def ingest_file(engine: Engine, source: GdeltSource, ts: datetime) -> RunResult:
    """Fetch, filter and store one export file, recording the outcome as an ingest run."""
    started_at = datetime.now(UTC)
    try:
        rows = source.fetch_export(ts)
        if rows is None:
            run = RunResult(ts, "skipped", error="GDELT has no file for this timestamp")
            with engine.begin() as conn:
                record_run(conn, run, started_at)
            return run

        events = [event for row in rows if (event := parse_row(row))]
        with engine.begin() as conn:
            inserted = store_events(conn, events)
            run = RunResult(ts, "succeeded", len(rows), len(events), inserted)
            record_run(conn, run, started_at)
        return run
    except Exception as exc:
        log.exception("ingest of %s failed", format_timestamp(ts))
        run = RunResult(ts, "failed", error=f"{type(exc).__name__}: {exc}"[:2000])
        with engine.begin() as conn:
            record_run(conn, run, started_at)
        return run


def already_handled(engine: Engine, ts: datetime) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                text("""
                    SELECT 1 FROM ingest_runs
                    WHERE file_timestamp = :ts AND status IN ('succeeded', 'skipped')
                """),
                {"ts": ts},
            ).first()
        )


def run_ingest(engine: Engine, source: GdeltSource) -> list[RunResult]:
    """Store the newest export file unless it is already stored."""
    latest = source.latest_timestamp()
    if already_handled(engine, latest):
        log.info("newest file %s is already stored", format_timestamp(latest))
        return []
    run = ingest_file(engine, source, latest)
    log.info(
        "%s %s: read %s, kept %s, inserted %s",
        format_timestamp(run.file_timestamp),
        run.status,
        run.rows_read,
        run.rows_kept,
        run.rows_inserted,
    )
    return [run]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = make_engine(get_settings().database_url)
    headers = {"User-Agent": "flashpoint-ingest (+https://github.com/InfinityTrip/flashpoint)"}
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        results = run_ingest(engine, GdeltSource(client))
    engine.dispose()
    # Non-zero exit marks the cron run as failed in Railway when every file failed.
    return 1 if results and all(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
