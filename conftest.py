"""
Repo-root pytest guard: pytest is for VentureGPS V2 tests ONLY.

Legacy tests (app/tests, app/calibration, app/reliability) are
script-style, import app.database.db at import time, and run against the
real DATABASE_URL -- collecting them can create tables and write rows in
the configured database. `testpaths` in pytest.ini covers a bare `pytest`,
but pytest deliberately does not apply --ignore/collect_ignore to paths
given explicitly on the command line, so `pytest app/tests` would still
import them. This hook closes that gap: every path argument must live
under app/v2, otherwise pytest exits before collecting anything.

Run legacy tests as before: python -m app.tests.<name>
"""

from pathlib import Path

import pytest

_V2_ROOT = Path(__file__).resolve().parent / "app" / "v2"


def pytest_sessionstart(session):
    invocation_dir = Path(session.config.invocation_params.dir)
    for arg in session.config.args:
        path = (invocation_dir / str(arg).split("::", 1)[0]).resolve()
        if path != _V2_ROOT and _V2_ROOT not in path.parents:
            pytest.exit(
                f"pytest is scoped to app/v2 (VentureGPS V2 tests only); refusing to "
                f"collect {arg!r}. Legacy tests are scripts: python -m app.tests.<name>",
                returncode=4,
            )
