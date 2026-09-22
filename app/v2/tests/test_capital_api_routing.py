"""Routing/OpenAPI/security checks for the Capital API that need no database at all: the router is inspected and
mounted in isolation, exactly as app/v2/tests/db/api_helpers.py does for the DB-backed tests."""

import ast
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.v2.api import router

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_the_four_expected_routes_are_registered():
    app = _make_app()
    paths = {(r.path, tuple(sorted(r.methods - {"HEAD"}))) for r in app.routes if hasattr(r, "methods") and r.path.startswith("/api/v2")}
    assert paths == {
        ("/api/v2/markets", ("GET",)),
        ("/api/v2/markets/{market_id}", ("GET",)),
        ("/api/v2/markets/{market_id}/capital/metrics", ("GET",)),
        ("/api/v2/markets/{market_id}/capital/signal", ("GET",)),
    }


def test_every_v2_route_is_get_only():
    app = _make_app()
    for r in app.routes:
        if not hasattr(r, "methods") or not r.path.startswith("/api/v2"):
            continue
        assert r.methods - {"HEAD", "OPTIONS"} == {"GET"}, r.path


def test_openapi_schema_generates_without_error():
    app = _make_app()
    schema = app.openapi()
    assert set(schema["paths"]) == {"/api/v2/markets", "/api/v2/markets/{market_id}",
                                    "/api/v2/markets/{market_id}/capital/metrics", "/api/v2/markets/{market_id}/capital/signal"}
    for path, methods in schema["paths"].items():
        assert set(methods) == {"get"}


def test_openapi_schema_documents_query_parameters():
    app = _make_app()
    schema = app.openapi()
    metrics_params = {p["name"] for p in schema["paths"]["/api/v2/markets/{market_id}/capital/metrics"]["get"]["parameters"]}
    assert {"market_id", "taxonomy_version", "start_date", "end_date"} <= metrics_params
    signal_params = {p["name"] for p in schema["paths"]["/api/v2/markets/{market_id}/capital/signal"]["get"]["parameters"]}
    assert {"market_id", "taxonomy_version", "as_of"} <= signal_params


def test_non_get_methods_are_refused():
    client = TestClient(_make_app())
    assert client.post("/api/v2/markets").status_code == 405
    assert client.delete("/api/v2/markets").status_code == 405
    assert client.put("/api/v2/markets").status_code == 405


def test_no_administrative_registration_or_write_endpoints_are_exposed():
    app = _make_app()
    paths = {r.path for r in app.routes if hasattr(r, "methods")}
    for banned in ("register", "candidate", "resolve", "classify", "promote", "ingest", "admin"):
        assert not any(banned in p for p in paths), banned


# ---------------- V1 stays untouched (static inspection; importing the full legacy app would run its own
# migrations against whatever DATABASE_URL is set, which this test suite must never risk -- see
# app/v2/tests/conftest.py's own env-stripping rationale)

def test_the_v2_router_is_mounted_additively_in_app_api_py():
    source = (REPO_ROOT / "app/api.py").read_text()
    assert "from app.v2.api import router as v2_capital_router" in source
    assert "app.include_router(v2_capital_router)" in source


def test_v1_route_decorators_are_still_present_after_the_v2_mount():
    source = (REPO_ROOT / "app/api.py").read_text()
    for known_v1_route in ('@app.get("/health")', '@app.get("/discover"', '@app.get("/rankings")', '@app.get("/compare"'):
        assert known_v1_route in source, known_v1_route


def test_the_v2_mount_does_not_sit_inside_any_conditional_or_function():
    tree = ast.parse((REPO_ROOT / "app/api.py").read_text())
    module_level_calls = {
        ast.dump(node.value.func) for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    }
    assert any("include_router" in c for c in module_level_calls)


def test_v2_api_declares_no_auth_dependency_matching_the_existing_public_endpoints():
    source = (REPO_ROOT / "app/v2/api.py").read_text()
    for banned in ("RequireAuth", "RequireAdmin", "RequireStartupMember", "get_current_user", "app.auth"):
        assert banned not in source
