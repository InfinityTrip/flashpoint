"""The ingest job: store every GDELT 15-minute export not yet stored, apply retention, exit.

Run by the Railway cron every 15 minutes: `python -m flashpoint.ingest`.
First load of the 35-day window: `python -m flashpoint.ingest --backfill`.
"""

import argparse
import itertools
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import astuple, dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import Connection, Engine, text

from flashpoint.db import make_engine
from flashpoint.gdelt import GdeltSource, format_timestamp
from flashpoint.parser import Event, parse_row
from flashpoint.settings import get_settings

log = logging.getLogger("flashpoint.ingest")

RETENTION_DAYS = 35
FILE_INTERVAL = timedelta(minutes=15)
# Files downloaded in parallel per batch; database writes stay sequential, in timestamp order.
DOWNLOAD_WORKERS = 8

# Same order as the fields of parser.Event.
STAGING_COLUMNS = (
    "global_event_id, date_added, event_date, root_code, event_code, goldstein,"
    " num_mentions, num_sources, num_articles, avg_tone, actor1_name, actor1_country,"
    " actor2_name, actor2_country, geo_type, place_name, country_code, lat, lon, source_url"
)

Fetched = list[list[str]] | None | Exception  # rows, "no such file", or the download error


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


def _fetch(source: GdeltSource, ts: datetime) -> tuple[datetime, Fetched]:
    """Download one file, returning the error instead of raising so a batch keeps going."""
    started_at = datetime.now(UTC)
    try:
        return started_at, source.fetch_export(ts)
    except Exception as exc:
        return started_at, exc


def _store(engine: Engine, ts: datetime, fetched: Fetched, started_at: datetime) -> RunResult:
    """Filter and store one downloaded file, recording the outcome as an ingest run."""
    try:
        if isinstance(fetched, Exception):
            raise fetched
        if fetched is None:
            run = RunResult(ts, "skipped", error="GDELT has no file for this timestamp")
            with engine.begin() as conn:
                record_run(conn, run, started_at)
            return run

        events = [event for row in fetched if (event := parse_row(row))]
        with engine.begin() as conn:
            inserted = store_events(conn, events)
            run = RunResult(ts, "succeeded", len(fetched), len(events), inserted)
            record_run(conn, run, started_at)
        return run
    except Exception as exc:
        log.error("ingest of %s failed: %s: %s", format_timestamp(ts), type(exc).__name__, exc)
        run = RunResult(ts, "failed", error=f"{type(exc).__name__}: {exc}"[:2000])
        with engine.begin() as conn:
            record_run(conn, run, started_at)
        return run


def ingest_file(engine: Engine, source: GdeltSource, ts: datetime) -> RunResult:
    """Fetch, filter and store one export file."""
    started_at, fetched = _fetch(source, ts)
    return _store(engine, ts, fetched, started_at)


def pending_timestamps(
    engine: Engine, latest: datetime, window_start: datetime, backfill: bool
) -> list[datetime]:
    """The 15-minute files up to `latest` that haven't been stored (or skipped as missing).

    - Backfill: every such file in the retention window.
    - Otherwise: the files after the newest one handled (catching up missed cron runs), going
      back further only to retry failures. With no history at all, just the newest file.
    """
    with engine.connect() as conn:
        handled = set(
            conn.execute(
                text("""
                    SELECT file_timestamp FROM ingest_runs
                    WHERE status IN ('succeeded', 'skipped') AND file_timestamp >= :start
                """),
                {"start": window_start},
            ).scalars()
        )
        newest_handled, oldest_failed = conn.execute(
            text("""
                SELECT
                    max(file_timestamp) FILTER (WHERE status <> 'failed'),
                    min(file_timestamp) FILTER (
                        WHERE status = 'failed' AND file_timestamp >= :start
                    )
                FROM ingest_runs
            """),
            {"start": window_start},
        ).one()

    start = window_start
    if not backfill:
        if newest_handled is None and oldest_failed is None:
            return [latest]
        candidates = [ts for ts in (newest_handled, oldest_failed) if ts is not None]
        start = max(window_start, min(candidates))

    pending = []
    ts = start
    while ts <= latest:
        if ts not in handled:
            pending.append(ts)
        ts += FILE_INTERVAL
    return pending


def apply_retention(engine: Engine, cutoff: datetime) -> tuple[int, int]:
    """Delete events reported before the cutoff, and ingest runs for files before it."""
    with engine.begin() as conn:
        events = conn.execute(
            text("DELETE FROM events WHERE date_added < :cutoff"), {"cutoff": cutoff}
        ).rowcount
        runs = conn.execute(
            text("DELETE FROM ingest_runs WHERE file_timestamp < :cutoff"), {"cutoff": cutoff}
        ).rowcount
    return events, runs


def run_ingest(
    engine: Engine,
    source: GdeltSource,
    *,
    backfill: bool = False,
    retention_days: int = RETENTION_DAYS,
) -> list[RunResult]:
    """Store every pending export file in timestamp order, then delete data past retention."""
    latest = source.latest_timestamp()
    cutoff = latest - timedelta(days=retention_days)
    # GDELT timestamps fall on exact 15-minute marks, so this is the first file in the window.
    window_start = cutoff + FILE_INTERVAL
    pending = pending_timestamps(engine, latest, window_start, backfill)
    if pending:
        log.info(
            "%d file(s) to ingest, %s to %s",
            len(pending),
            format_timestamp(pending[0]),
            format_timestamp(pending[-1]),
        )
    else:
        log.info("nothing new: newest file %s is already stored", format_timestamp(latest))

    results: list[RunResult] = []
    workers = DOWNLOAD_WORKERS if len(pending) > 1 else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Small batches keep memory bounded: download a batch in parallel, store it in order.
        for batch in itertools.batched(pending, workers * 2, strict=False):
            downloads = pool.map(lambda ts: _fetch(source, ts), batch)
            for ts, (started_at, fetched) in zip(batch, downloads, strict=True):
                run = _store(engine, ts, fetched, started_at)
                results.append(run)
                if len(pending) <= 5:
                    log.info(
                        "%s %s: read %s, kept %s, inserted %s",
                        format_timestamp(ts),
                        run.status,
                        run.rows_read,
                        run.rows_kept,
                        run.rows_inserted,
                    )
            if len(pending) > 5:
                inserted = sum(r.rows_inserted or 0 for r in results)
                log.info("progress: %d/%d files, %d events", len(results), len(pending), inserted)

    deleted_events, deleted_runs = apply_retention(engine, cutoff)
    if deleted_events or deleted_runs:
        log.info("retention: deleted %d events and %d ingest runs", deleted_events, deleted_runs)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Store new GDELT export files.")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=f"load every missing file in the {RETENTION_DAYS}-day window, not just recent ones",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    engine = make_engine(get_settings().database_url)
    headers = {"User-Agent": "flashpoint-ingest (+https://github.com/InfinityTrip/flashpoint)"}
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        results = run_ingest(engine, GdeltSource(client), backfill=args.backfill)
    engine.dispose()
    # Non-zero exit marks the cron run as failed in Railway when every file failed.
    return 1 if results and all(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
