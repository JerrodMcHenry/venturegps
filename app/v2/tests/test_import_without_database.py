"""
Importing V2 DB/config modules must need no database, no environment, no AI
config, and must not connect. Run in a clean subprocess with create_engine and
psycopg2.connect booby-trapped BEFORE the imports.
"""

import json
import os
import subprocess
import sys

from app.v2.tests.architecture.boundary_scanner import REPO_ROOT

MODULES = [
    "app.v2",
    "app.v2.config",
    "app.v2.db",
    "app.v2.db.engine",
    "app.v2.db.metadata",
    "app.v2.db.scope",
    "app.v2.db.locks",
    "app.v2.db.tables",
    "app.v2.repositories.sources",
    "app.v2.repositories.raw_payloads",
    "app.v2.repositories.observations",
    "app.v2.domain.payload",
    "app.v2.migrations.versions.0003_create_raw_payload_and_observation",
    "app.v2.migrations.versions.0002_create_source",
    "app.v2.migrations.versions.0001_establish_v2_namespace",
]

SCRIPT = """
import importlib, json, sys
import sqlalchemy, psycopg2
def boom(*a, **k): raise AssertionError("database access attempted at import time")
sqlalchemy.create_engine = boom
psycopg2.connect = boom
for name in json.loads(sys.argv[1]):
    importlib.import_module(name)
bad = [m for m in sys.modules if m.split(".")[0] in ("openai","anthropic","tavily","dotenv")
       or m.startswith(("app.database","app.ai","app.api","app.models","app.auth","app.workflows"))]
print("RESULT:" + json.dumps(bad))
"""

STRIPPED = ("DATABASE_URL", "V2_DATABASE_URL", "V2_TEST_DATABASE_URL",
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TAVILY_API_KEY")


def test_v2_db_and_config_import_without_environment_or_connection():
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-c", SCRIPT, json.dumps(MODULES)],
                          cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    line = next(l for l in done.stdout.splitlines() if l.startswith("RESULT:"))
    assert json.loads(line[len("RESULT:"):]) == []
