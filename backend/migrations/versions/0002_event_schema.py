"""Event schema: lookup tables (regions, countries, event types), events, ingest runs.

Revision ID: 0002
Revises: 0001
"""

import csv
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

COUNTRIES_CSV = Path(__file__).resolve().parent.parent / "data" / "countries.csv"


def upgrade() -> None:
    op.execute("""
        -- The 7 World Bank regions, keyed by the World Bank's own codes.
        CREATE TABLE regions (
            id   text PRIMARY KEY,
            name text NOT NULL UNIQUE
        );

        INSERT INTO regions (id, name) VALUES
            ('EAS', 'East Asia & Pacific'),
            ('ECS', 'Europe & Central Asia'),
            ('LCN', 'Latin America & Caribbean'),
            ('MEA', 'Middle East, North Africa, Afghanistan & Pakistan'),
            ('NAC', 'North America'),
            ('SAS', 'South Asia'),
            ('SSF', 'Sub-Saharan Africa');

        -- GDELT identifies countries by FIPS 10-4 code (SU = Sudan, not ISO's SD).
        CREATE TABLE countries (
            fips_code text PRIMARY KEY,
            iso2      text,
            iso3      text,
            name      text NOT NULL,
            region_id text REFERENCES regions (id)
        );
        CREATE INDEX countries_region_idx ON countries (region_id);

        -- The 7 CAMEO root codes Flashpoint keeps: 14 (protest) to 20 (mass violence).
        CREATE TABLE event_types (
            root_code smallint PRIMARY KEY CHECK (root_code BETWEEN 14 AND 20),
            name      text NOT NULL,
            colour    text NOT NULL
        );

        INSERT INTO event_types (root_code, name, colour) VALUES
            (14, 'Protest',                  '#facc15'),
            (15, 'Exhibit military posture', '#a3e635'),
            (16, 'Reduce relations',         '#38bdf8'),
            (17, 'Coerce',                   '#fb923c'),
            (18, 'Assault',                  '#f43f5e'),
            (19, 'Fight',                    '#dc2626'),
            (20, 'Mass violence',            '#c026d3');

        -- One row per GDELT event: a news-reported action, machine-coded from an article.
        -- Append-only and unique by GDELT's id; about 20 of GDELT's 61 columns are kept.
        CREATE TABLE events (
            global_event_id bigint PRIMARY KEY,
            date_added      timestamptz NOT NULL,   -- when GDELT recorded it (DATEADDED)
            event_date      date NOT NULL,          -- the date the event itself happened (SQLDATE)
            root_code       smallint NOT NULL REFERENCES event_types (root_code),
            event_code      text NOT NULL,          -- full CAMEO code, e.g. 193
            goldstein       real,                   -- -10 (most destabilising) to +10
            num_mentions    integer,
            num_sources     integer,
            num_articles    integer,
            avg_tone        real,
            actor1_name     text,
            actor1_country  text,                   -- CAMEO actor country code, e.g. USA
            actor2_name     text,
            actor2_country  text,
            geo_type        smallint NOT NULL, -- 1 country 2 US state 3 US city 4 city 5 province
            place_name      text,
            country_code    text REFERENCES countries (fips_code),
            location        geometry (Point, 4326) NOT NULL,
            source_url      text
        );

        CREATE INDEX events_location_idx ON events USING gist (location);
        CREATE INDEX events_date_added_idx ON events (date_added);
        CREATE INDEX events_country_date_idx ON events (country_code, date_added);
        CREATE INDEX events_type_date_idx ON events (root_code, date_added);

        -- One row per GDELT 15-minute file the ingest job has handled.
        CREATE TABLE ingest_runs (
            id             bigserial PRIMARY KEY,
            file_timestamp timestamptz NOT NULL UNIQUE,
            status         text NOT NULL CHECK (status IN ('succeeded', 'skipped', 'failed')),
            started_at     timestamptz NOT NULL,
            finished_at    timestamptz NOT NULL,
            rows_read      integer,
            rows_kept      integer,
            rows_inserted  integer,
            error          text
        );
        CREATE INDEX ingest_runs_status_idx ON ingest_runs (status, file_timestamp);
    """)

    with COUNTRIES_CSV.open(encoding="utf-8", newline="") as f:
        countries = [{k: (v or None) for k, v in row.items()} for row in csv.DictReader(f)]
    op.get_bind().execute(
        text("""
            INSERT INTO countries (fips_code, iso2, iso3, name, region_id)
            VALUES (:fips_code, :iso2, :iso3, :name, :region_id)
        """),
        countries,
    )


def downgrade() -> None:
    op.execute("""
        DROP TABLE ingest_runs;
        DROP TABLE events;
        DROP TABLE event_types;
        DROP TABLE countries;
        DROP TABLE regions;
    """)
