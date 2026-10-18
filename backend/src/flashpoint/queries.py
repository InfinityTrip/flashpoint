"""Hand-written SQL, one function per API need."""

from sqlalchemy import Connection, text


def database_is_reachable(conn: Connection) -> bool:
    return conn.execute(text("SELECT 1")).scalar_one() == 1
