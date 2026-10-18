from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from flashpoint.api.app import create_app
from flashpoint.ingest import run_ingest
from flashpoint.settings import Settings
from tests.gdelt_fixtures import FakeGdelt, gdelt_row


def quarter_hour_ago(minutes: int) -> datetime:
    """A GDELT-style timestamp (on a 15-minute mark) at least `minutes` in the past."""
    ts = datetime.now(UTC) - timedelta(minutes=minutes)
    return ts.replace(minute=ts.minute - ts.minute % 15, second=0, microsecond=0)


def test_health_is_ok_when_data_is_fresh(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    ts = quarter_hour_ago(10)
    gdelt.publish(ts, [gdelt_row(added=ts)])
    run_ingest(engine, gdelt.source())

    response = client.get("/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["database"]) == ("ok", "ok")
    assert datetime.fromisoformat(body["latest_data_at"]) == ts
    assert 10 <= body["minutes_since_update"] < 30


def test_health_is_degraded_when_data_is_over_an_hour_old(
    engine: Engine, gdelt: FakeGdelt, client: TestClient
) -> None:
    ts = quarter_hour_ago(75)
    gdelt.publish(ts, [gdelt_row(added=ts)])
    run_ingest(engine, gdelt.source())

    body = client.get("/v1/health").json()

    assert body["status"] == "degraded"
    assert body["minutes_since_update"] > 60


def test_health_is_degraded_before_any_data_arrives(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "database": "ok",
        "latest_data_at": None,
        "minutes_since_update": None,
    }


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
    assert response.json()["status"] == "down"
    assert response.json()["database"] == "unreachable"


def test_settings_accept_plain_postgres_urls() -> None:
    settings = Settings(database_url="postgresql://user:pw@host/db?sslmode=require")

    assert settings.database_url == "postgresql+psycopg://user:pw@host/db?sslmode=require"
