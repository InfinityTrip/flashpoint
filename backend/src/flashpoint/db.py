"""Database access: one SQLAlchemy Core engine and plain SQL. There is no ORM."""

from sqlalchemy import Engine, create_engine


def make_engine(database_url: str) -> Engine:
    # pool_pre_ping replaces connections that died while Neon was scaled to zero.
    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
