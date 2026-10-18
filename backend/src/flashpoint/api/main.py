"""ASGI entry point: `uvicorn flashpoint.api.main:app`."""

from flashpoint.api.app import create_app

app = create_app()
