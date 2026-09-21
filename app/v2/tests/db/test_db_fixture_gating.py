"""
End-to-end proof of the gating behavior: pytest is run in a subprocess against
a DB test module with different environments. No real database is ever reached
(the URLs used here point at a dead port or are refused before connecting).
"""

import os
import subprocess
import sys

import pytest

from app.v2.tests.architecture.boundary_scanner import REPO_ROOT

DEAD_PROD = "postgresql://prod:prod@127.0.0.1:1/venturegps_prod"
TARGET = "app/v2/tests/db/test_migrations.py"


def run(extra_env: dict[str, str], *, drop=()):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("V2_") and k != "DATABASE_URL" and k not in drop}
    env.update(extra_env)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", TARGET, "-q", "-p", "no:cacheprovider", "-x"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    return done.returncode, done.stdout + done.stderr


def test_unset_test_url_skips_db_tests():
    code, out = run({})
    assert code == 0 and "skipped" in out and "V2_TEST_DATABASE_URL is not set" in out


def test_production_database_url_is_never_a_fallback():
    # DATABASE_URL and V2_DATABASE_URL are set, V2_TEST_DATABASE_URL is not: must skip, not connect.
    code, out = run({"DATABASE_URL": DEAD_PROD, "V2_DATABASE_URL": DEAD_PROD})
    assert code == 0 and "skipped" in out
    assert "OperationalError" not in out and "Connection refused" not in out


def test_require_flag_turns_skip_into_failure():
    code, out = run({"V2_REQUIRE_DB_TESTS": "1"})
    assert code != 0 and "V2_REQUIRE_DB_TESTS=1" in out


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:pw@127.0.0.1:1/venturegps_prod",
        "postgresql://u:pw@127.0.0.1:1/postgres",
        "postgresql://u:pw@db.example.com:5432/venturegps_v2_test",
    ],
)
def test_unsafe_test_url_fails_loudly_and_never_connects(url):
    code, out = run({"V2_TEST_DATABASE_URL": url})
    assert code != 0 and "REFUSING to run V2 database tests" in out
    assert "skipped" not in out.split("REFUSING")[0].splitlines()[-1] if out else True
    assert "Connection refused" not in out and "pw" not in out.replace("REFUSING", "")


def test_test_url_equal_to_production_name_is_refused():
    code, out = run({
        "V2_TEST_DATABASE_URL": "postgresql://u:pw@127.0.0.1:1/venturegps_v2_test",
        "DATABASE_URL": "postgresql://a:b@prod.internal:5432/venturegps_v2_test",
    })
    assert code != 0 and "REFUSING" in out and "DATABASE_URL" in out
