"""
Shared fixtures for the V2 suite.

Every V2 test runs with AI/search credentials REMOVED from the process
environment (restored afterwards), so the deterministic suite can never
silently depend on them. CI should additionally run the suite with
`env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u TAVILY_API_KEY pytest`.
"""

import os

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES


@pytest.fixture(scope="session", autouse=True)
def _ai_credentials_absent():
    saved = {name: os.environ.pop(name) for name in DEFAULT_RULES.forbidden_env_names if name in os.environ}
    yield
    os.environ.update(saved)
