"""Evidence persistence (Increment 5) stays inside the AI/determinism and purity boundaries."""

from app.v2.tests.architecture.boundary_scanner import (
    REPO_ROOT,
    is_forbidden_loaded_for_deterministic,
    scan_source,
    scan_tree,
)
from app.v2.tests.architecture.runtime_probe import run_import_probe

FILES = ("app/v2/repositories/raw_payloads.py", "app/v2/repositories/observations.py", "app/v2/repositories/_db.py")


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


def test_the_evidence_modules_are_scanned_and_clean():
    result = scan_tree(REPO_ROOT)
    scanned = set(result.files_scanned)
    assert set(FILES) | {"app/v2/domain/payload.py", "app/v2/migrations/versions/0003_create_raw_payload_and_observation.py"} <= scanned
    assert not [v for v in result.violations if v.path in FILES or v.path.endswith("payload.py")]


def test_the_boundary_rules_really_apply_to_the_evidence_repositories():
    for path in FILES[:2]:
        real = (REPO_ROOT / path).read_text()
        assert scan_source(real, path) == []
        assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import proposer\n", path)
        assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport anthropic\n", path)
        assert "deterministic-imports-legacy" in rules_of(real + "\nfrom app.ai import scoring\n", path)
        assert "deterministic-references-ai-env" in rules_of(real + '\nk = "ANTHROPIC_API_KEY"\n', path)


def test_ai_code_cannot_reach_evidence_persistence():
    for source in ("from app.v2.repositories.observations import store_observation", "from app.v2.repositories import raw_payloads",
                   "from app.v2.db.tables import observation_table", "import app.v2.repositories.raw_payloads"):
        assert "ai-imports-persistence" in rules_of(source, "app/v2/ai/adapter.py"), source


def test_the_pure_domain_stays_pure_with_the_new_payload_module():
    payload = (REPO_ROOT / "app/v2/domain/payload.py").read_text()
    assert scan_source(payload, "app/v2/domain/payload.py") == []
    for bad in ("import sqlalchemy", "from app.v2.repositories import observations", "from app.v2.db.tables import raw_payload_table",
                "import os", "import hashlib_is_fine_but_not_this\nimport socket"):
        assert "pure-imports-forbidden" in rules_of(bad, "app/v2/domain/payload.py"), bad
    assert "layer-violation" in rules_of("from app.v2.observations import hashing", "app/v2/domain/payload.py")


def test_importing_evidence_persistence_loads_no_ai_provider_or_legacy_module():
    probe = run_import_probe(["app.v2.repositories.raw_payloads", "app.v2.repositories.observations", "app.v2.domain.payload"], cwd=REPO_ROOT)
    assert probe.failed == {}
    assert [m for m in probe.loaded if is_forbidden_loaded_for_deterministic(m)] == []
