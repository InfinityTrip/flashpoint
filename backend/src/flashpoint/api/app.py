"""The public /v1/ HTTP API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from flashpoint.api import health
from flashpoint.db import make_engine
from flashpoint.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Flashpoint API",
        version="1",
        description="News-reported conflict events worldwide, from the GDELT 2.0 event feed.",
    )
    app.state.engine = make_engine(settings.database_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/v1")
    return app
