"""CAMEO actions: the plain-words description of each event code under roots 14-20.

Revision ID: 0003
Revises: 0002
"""

import csv
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# From GDELT's CAMEO.eventcodes.txt, with "not specified below" dropped from the wording.
CAMEO_CSV = Path(__file__).resolve().parent.parent / "data" / "cameo_actions.csv"


def upgrade() -> None:
    # events.event_code deliberately has no foreign key to this table: a code missing here
    # should still be stored (the detail card falls back to the conflict type's name), not
    # make the whole 15-minute file fail.
    op.execute("""
        CREATE TABLE cameo_actions (
            event_code  text PRIMARY KEY,
            root_code   smallint NOT NULL REFERENCES event_types (root_code),
            description text NOT NULL
        );
    """)
    with CAMEO_CSV.open(encoding="utf-8", newline="") as f:
        actions = list(csv.DictReader(f))
    op.get_bind().execute(
        text("""
            INSERT INTO cameo_actions (event_code, root_code, description)
            VALUES (:event_code, CAST(:root_code AS smallint), :description)
        """),
        actions,
    )


def downgrade() -> None:
    op.execute("DROP TABLE cameo_actions;")
