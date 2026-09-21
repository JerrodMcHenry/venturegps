"""Processing stays deterministic: no AI, no network, no worker/queue/scheduler framework, pure domain stays pure."""

from pathlib import Path

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import (
    REPO_ROOT,
    is_forbidden_loaded_for_network,
    scan_source,
    scan_tree,
)
from app.v2.tests.architecture.runtime_probe import run_import_probe

REPO_FILE = "app/v2/repositories/processing_attempts.py"
DOMAIN_FILES = ("app/v2/domain/processing_attempt.py", "app/v2/domain/processing.py")
FRAMEWORKS = ["import celery", "from celery import Celery", "import rq", "import arq", "import dramatiq", "import huey", "import kombu",
              "import redis", "import apscheduler", "from apscheduler.schedulers.background import BackgroundScheduler",
              "import schedule", "import sched", "import taskiq", "import prefect", "import airflow", "import dask", "import ray",
              'import importlib\nimportlib.import_module("celery")']


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


def test_the_processing_modules_are_scanned_and_clean():
    result = scan_tree(REPO_ROOT)
    assert {REPO_FILE, *DOMAIN_FILES, "app/v2/migrations/versions/0005_create_processing_attempt.py"} <= set(result.files_scanned)
    assert not [v for v in result.violations if v.path == REPO_FILE or v.path in DOMAIN_FILES]


def test_the_rules_bite_on_the_processing_repository_path():
    real = (REPO_ROOT / REPO_FILE).read_text()
    assert scan_source(real, REPO_FILE) == []
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import proposer\n", REPO_FILE)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", REPO_FILE)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport anthropic\n", REPO_FILE)
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "OPENAI_API_KEY"\n', REPO_FILE)
    assert "network-import-forbidden" in rules_of(real + "\nimport httpx\n", REPO_FILE)
    assert "deterministic-imports-legacy" in rules_of(real + "\nfrom app.database.db import engine\n", REPO_FILE)


@pytest.mark.parametrize("source", FRAMEWORKS)
@pytest.mark.parametrize("path", [REPO_FILE, "app/v2/ingestion/service.py", "app/v2/core/anything.py", "app/v2/domain/processing.py"])
def test_no_worker_queue_or_scheduler_framework_can_be_imported(source, path):
    assert "deterministic-imports-worker-framework" in rules_of(source, path)


def test_framework_matching_respects_package_boundaries():
    assert rules_of("import ray_tracing_lib", "app/v2/core/x.py") == set()
    assert rules_of("from schedule_utils import x", "app/v2/core/x.py") == set()
    assert "redis" in DEFAULT_RULES.worker_framework_prefixes


def test_no_worker_package_or_framework_was_introduced():
    assert not (REPO_ROOT / "app/v2/workers").exists()
    requirements = (REPO_ROOT / "requirements.txt").read_text().lower()
    for name in ("celery", "dramatiq", "apscheduler", "redis", "kombu", "arq==", "rq=="):
        assert name not in requirements, name


@pytest.mark.parametrize("path", DOMAIN_FILES)
def test_the_pure_domain_stays_pure(path):
    real = (REPO_ROOT / path).read_text()
    assert scan_source(real, path) == []
    for bad in ("import sqlalchemy", "import os", "import socket", "from app.v2.repositories import processing_attempts",
                "from app.v2.db.tables import processing_attempt_table", "import threading_is_fine\nimport requests"):
        assert "pure-imports-forbidden" in rules_of(bad, path), bad


def test_ai_cannot_reach_processing_persistence():
    for source in ("from app.v2.repositories.processing_attempts import start_processing", "from app.v2.repositories import processing_attempts",
                   "from app.v2.db.tables import processing_attempt_table"):
        assert "ai-imports-persistence" in rules_of(source, "app/v2/ai/adapter.py"), source


def test_importing_processing_persistence_loads_no_ai_network_or_legacy_module():
    probe = run_import_probe(["app.v2.repositories.processing_attempts", "app.v2.domain.processing_attempt", "app.v2.domain.processing"], cwd=REPO_ROOT)
    assert probe.failed == {}
    assert [m for m in probe.loaded if is_forbidden_loaded_for_network(m)] == []
