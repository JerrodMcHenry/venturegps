"""Shared HTTP test client for the V2 Capital API: mounts app.v2.api.router in isolation (NEVER the full legacy
app.api, which runs ~50 legacy migrations at import time against whatever DATABASE_URL happens to be set) and
overrides the engine dependency to point at the caller's disposable test database, never the process-wide
get_engine() singleton."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.v2.api import _engine_or_503, router


def client_for(engine) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_engine_or_503] = lambda: engine
    return TestClient(app)
