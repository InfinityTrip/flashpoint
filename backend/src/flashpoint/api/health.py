from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from flashpoint import queries

router = APIRouter()


class Health(BaseModel):
    status: str  # "ok" or "down"
    database: str  # "ok" or "unreachable"


@router.get("/health", response_model=Health, summary="Is the API and its database up?")
def health(request: Request, response: Response) -> Health:
    try:
        with request.app.state.engine.connect() as conn:
            queries.database_is_reachable(conn)
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(status="down", database="unreachable")
    return Health(status="ok", database="ok")
