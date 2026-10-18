from datetime import datetime

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from flashpoint import queries

router = APIRouter()

# Data older than this means the ingest job (or GDELT itself) has stalled.
STALE_AFTER_MINUTES = 60


class Health(BaseModel):
    status: str  # "ok", "degraded" (data is stale) or "down" (database unreachable)
    database: str  # "ok" or "unreachable"
    latest_data_at: datetime | None = None  # timestamp of the newest GDELT file stored
    minutes_since_update: float | None = None


@router.get("/health", response_model=Health, summary="Is the API up, and how fresh is the data?")
def health(request: Request, response: Response) -> Health:
    try:
        with request.app.state.engine.connect() as conn:
            freshness = queries.data_freshness(conn)
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(status="down", database="unreachable")

    minutes = freshness["minutes_since_update"]
    stale = minutes is None or minutes > STALE_AFTER_MINUTES
    return Health(
        status="degraded" if stale else "ok",
        database="ok",
        latest_data_at=freshness["latest_data_at"],
        minutes_since_update=None if minutes is None else round(minutes, 1),
    )
