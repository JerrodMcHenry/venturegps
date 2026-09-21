"""The real `alembic` CLI with NO database configured must fail clearly and never guess a target."""

import os
import subprocess
import sys

from app.v2.tests.architecture.boundary_scanner import REPO_ROOT

STRIPPED = ("DATABASE_URL", "V2_DATABASE_URL", "V2_TEST_DATABASE_URL")


def test_cli_without_a_configured_database_fails_without_connecting():
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=REPO_ROOT,
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode != 0
    assert "no database configured" in done.stderr
    assert "Connection refused" not in done.stderr


def test_cli_never_reads_the_test_database_url():
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    env["V2_TEST_DATABASE_URL"] = "postgresql://u@127.0.0.1:1/venturegps_v2_test"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=REPO_ROOT,
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode != 0 and "no database configured" in done.stderr
