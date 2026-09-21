"""
Shared fixtures for the V2 suite.

Every V2 test runs with AI/search credentials AND production database URLs
(DATABASE_URL, V2_DATABASE_URL) REMOVED from the process environment
(restored afterwards). So the deterministic suite can never silently depend
on them, and DB tests can never fall back to a production database by
accident. The values are snapshotted at import time (before removal) only so
the test-database guard can refuse a test URL that points at production.

CI should additionally run the suite with
`env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u TAVILY_API_KEY pytest`.
"""

import os

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES

PRODUCTION_URL_ENVS = ("DATABASE_URL", "V2_DATABASE_URL")

# Snapshot BEFORE the session fixture removes them.
_PRODUCTION_URL_SNAPSHOT = {
    name: os.environ[name] for name in PRODUCTION_URL_ENVS if os.environ.get(name)
}


@pytest.fixture(scope="session", autouse=True)
def _isolated_environment():
    names = tuple(DEFAULT_RULES.forbidden_env_names) + PRODUCTION_URL_ENVS
    saved = {name: os.environ.pop(name) for name in names if name in os.environ}
    yield
    os.environ.update(saved)


@pytest.fixture(scope="session")
def production_urls() -> dict[str, str]:
    return dict(_PRODUCTION_URL_SNAPSHOT)
