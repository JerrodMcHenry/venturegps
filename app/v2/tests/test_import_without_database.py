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
    "app.v2.repositories.sightings",
    "app.v2.repositories.processing_attempts",
    "app.v2.repositories.company_candidates",
    "app.v2.repositories.financing_event_candidates",
    "app.v2.domain.financing",
    "app.v2.candidates.financing_evidence",
    "app.v2.migrations.versions.0008_create_financing_event_candidate",
    "app.v2.repositories.companies",
    "app.v2.domain.company",
    "app.v2.domain.resolution",
    "app.v2.resolution",
    "app.v2.resolution.errors",
    "app.v2.resolution._writes",
    "app.v2.resolution.promotion",
    "app.v2.resolution.rules",
    "app.v2.migrations.versions.0007_create_resolution_and_company",
    "app.v2.domain.candidate",
    "app.v2.candidates",
    "app.v2.candidates.proposer",
    "app.v2.candidates.evidence",
    "app.v2.candidates.service",
    "app.v2.migrations.versions.0006_create_company_candidate",
    "app.v2.domain.processing_attempt",
    "app.v2.migrations.versions.0005_create_processing_attempt",
    "app.v2.domain.sighting",
    "app.v2.ingestion",
    "app.v2.ingestion.models",
    "app.v2.ingestion.errors",
    "app.v2.ingestion.service",
    "app.v2.migrations.versions.0004_create_observation_sighting",
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
