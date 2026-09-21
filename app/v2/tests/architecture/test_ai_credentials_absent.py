"""V2 tests run with AI/search credentials removed (see ../conftest.py)."""

import os

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES


def test_ai_credentials_are_absent_during_v2_tests():
    present = [name for name in DEFAULT_RULES.forbidden_env_names if name in os.environ]
    assert present == []
