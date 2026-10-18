from fastapi.testclient import TestClient

from flashpoint.api.app import create_app
from flashpoint.settings import Settings


def test_health_reports_database_reachable(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_unreachable_database_as_503() -> None:
    # Port 1 has nothing listening, so the connection fails straight away.
    app = create_app(
        Settings(
            database_url="postgresql+psycopg://nobody:nothing@127.0.0.1:1/none?connect_timeout=2"
        )
    )
    with TestClient(app) as client:
        response = client.get("/v1/health")

    assert response.status_code == 503
    assert response.json() == {"status": "down", "database": "unreachable"}


def test_settings_accept_plain_postgres_urls() -> None:
    settings = Settings(database_url="postgresql://user:pw@host/db?sslmode=require")

    assert settings.database_url == "postgresql+psycopg://user:pw@host/db?sslmode=require"
