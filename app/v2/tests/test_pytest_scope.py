"""
Pytest must stay scoped to V2. These run pytest in a subprocess against
legacy paths and assert nothing is collected and no legacy module is
imported. DATABASE_URL is pointed at a dead port as a belt-and-braces
guard: even if the scoping broke, nothing here could reach a real database.
"""

import os
import subprocess
import sys

import pytest

from app.v2.tests.architecture.boundary_scanner import REPO_ROOT

_DEAD_DB = "postgresql://invalid:invalid@127.0.0.1:1/none"


def _pytest(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": _DEAD_DB, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


def test_bare_pytest_collects_only_v2_tests():
    out = _pytest("--collect-only", "-q").stdout
    node_ids = [line for line in out.splitlines() if "::" in line]
    assert node_ids, out
    assert all(line.startswith("app/v2/tests/") for line in node_ids)


@pytest.mark.parametrize(
    "target",
    [
        "app/tests",
        "app/tests/test_startup_write_path.py",
        "app/tests/test_startup_write_path.py::test_concurrent_new_company_resolves_to_one_startup",
        "app/calibration",
        "app/reliability",
        "app",
        ".",
    ],
)
def test_explicit_legacy_paths_are_refused_before_collection(target):
    completed = _pytest("--collect-only", "-q", target)
    assert completed.returncode == 4, completed.stdout + completed.stderr
    assert "scoped to app/v2" in completed.stdout + completed.stderr
    assert "tests collected" not in completed.stdout
    assert "sqlalchemy" not in (completed.stdout + completed.stderr).lower()


def test_mixing_v2_and_legacy_paths_is_refused():
    completed = _pytest("--collect-only", "-q", "app/v2/tests", "app/tests")
    assert completed.returncode == 4


def test_explicit_v2_paths_still_work():
    completed = _pytest("--collect-only", "-q", "app/v2/tests/architecture")
    assert completed.returncode == 0
    assert "tests collected" in completed.stdout
