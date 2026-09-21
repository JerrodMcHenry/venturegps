"""
Source persistence (Increment 4) stays inside the AI/determinism and purity
boundaries: the repository is deterministic code that AI and the pure domain
can never reach, and it reaches neither.
"""

from app.v2.tests.architecture.boundary_scanner import (
    REPO_ROOT,
    is_forbidden_loaded_for_deterministic,
    scan_source,
    scan_tree,
)
from app.v2.tests.architecture.runtime_probe import run_import_probe

REPO_FILE = "app/v2/repositories/sources.py"
TABLES_FILE = "app/v2/db/tables.py"


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


def test_the_real_source_persistence_modules_are_scanned_and_clean():
    result = scan_tree(REPO_ROOT)
    scanned = set(result.files_scanned)
    assert {REPO_FILE, TABLES_FILE, "app/v2/repositories/errors.py", "app/v2/migrations/versions/0002_create_source.py"} <= scanned
    assert not [v for v in result.violations if v.path.startswith(("app/v2/repositories/", "app/v2/db/"))]


def test_the_boundary_rules_really_apply_to_the_repository_path():
    real = (REPO_ROOT / REPO_FILE).read_text()
    assert scan_source(real, REPO_FILE) == []
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import proposer\n", REPO_FILE)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", REPO_FILE)
    assert "deterministic-imports-legacy" in rules_of(real + "\nfrom app.database.db import engine\n", REPO_FILE)
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "OPENAI_API_KEY"\n', REPO_FILE)


def test_ai_code_cannot_reach_the_source_repository_or_tables():
    for source in (
        "from app.v2.repositories.sources import register_source",
        "from app.v2.repositories import sources",
        "import app.v2.repositories.sources",
        "from app.v2.db.tables import source_table",
        "from app.v2.db import tables",
        "from sqlalchemy import select",
    ):
        assert "ai-imports-persistence" in rules_of(source, "app/v2/ai/adapter.py"), source


def test_the_pure_domain_cannot_import_persistence():
    for path in ("app/v2/domain/source.py", "app/v2/domain/observation.py", "app/v2/observations/hashing.py"):
        for source in (
            "from app.v2.repositories import sources",
            "from app.v2.repositories.sources import register_source",
            "from app.v2.db.tables import source_table",
            "from app.v2.db import engine",
            "import sqlalchemy",
        ):
            assert "pure-imports-forbidden" in rules_of(source, path), (path, source)


def test_importing_source_persistence_loads_no_ai_provider_or_legacy_module():
    probe = run_import_probe(["app.v2.repositories.sources", "app.v2.repositories.errors", "app.v2.db.tables"], cwd=REPO_ROOT)
    assert probe.failed == {}
    assert [m for m in probe.loaded if is_forbidden_loaded_for_deterministic(m)] == []
