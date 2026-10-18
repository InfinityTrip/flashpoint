"""Shared test setup: a real, migrated PostGIS database and an HTTP client for the API.

Point TEST_DATABASE_URL at an empty database you don't mind wiping. The default matches
the `flashpoint_test` database that docker compose creates.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from flashpoint.api.app import create_app
from flashpoint.settings import Settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://flashpoint:flashpoint@localhost:5432/flashpoint_test",
)


@pytest.fixture(scope="session")
def database_url() -> str:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = Settings(database_url=TEST_DATABASE_URL).database_url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    return config.attributes["database_url"]


@pytest.fixture
def client(database_url: str) -> TestClient:
    app = create_app(Settings(database_url=database_url))
    with TestClient(app) as test_client:
        yield test_client
