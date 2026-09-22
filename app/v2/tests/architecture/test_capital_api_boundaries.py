"""
The Capital API boundary, structurally (Increment 14):

  - app/v2/api.py (and app/v2/api_schemas.py) import NO write-capable function: no candidate write repository,
    no promotion/resolution/classification service, no ingestion service, no market/taxonomy registration
  - the write-scan finds no canonical-table write anywhere in either module
  - no AI, no provider SDK, no worker framework is reachable from the API layer
  - no Clerk auth dependency is declared (these are public reads, matching /discover, /rankings)
  - the legacy-import allowlist stays closed to everything except app.observability
"""

import ast
import re

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import REPO_ROOT, scan_source, scan_tree
from app.v2.tests.architecture.canonical_write_scan import canonical_writes
from app.v2.tests.architecture.runtime_probe import run_import_probe

API = "app/v2/api.py"
SCHEMAS = "app/v2/api_schemas.py"
AI = "app/v2/ai/adapter.py"

# Every write-capable function/module the API must never call or import, across every canonical/candidate
# boundary built in Increments 6-12.
FORBIDDEN_WRITE_CALLS = (
    "persist_financing_event_candidates", "store_company_candidates", "persist_verified_candidates",
    "create_event_from_candidate", "attach_candidate_to_event", "reject_candidate", "defer_candidate",
    "create_company_from_candidate", "attach_candidate_to_company",
    "classify_company", "insert_classification",
    "register_market", "register_taxonomy_version",
    "ingest_evidence", "store_raw_payload", "register_source",
    "insert_event", "insert_decision", "insert_stage", "insert_type", "insert_verified_round_amount", "insert_date",
)
FORBIDDEN_MODULE_IMPORTS = (
    "app.v2.resolution.promotion", "app.v2.resolution._writes",
    "app.v2.financing_resolution.promotion", "app.v2.financing_resolution._writes",
    "app.v2.classification.service", "app.v2.classification._writes",
    "app.v2.candidates.service", "app.v2.repositories.company_candidates",
    "app.v2.repositories.financing_event_candidates", "app.v2.ingestion.service",
)


def source_of(path):
    return (REPO_ROOT / path).read_text()


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


# ---------------- no writes, anywhere

def test_the_api_writes_no_canonical_table():
    assert canonical_writes(source_of(API), API) == []
    assert canonical_writes(source_of(SCHEMAS), SCHEMAS) == []


def test_the_api_calls_no_write_capable_function():
    code = re.sub(r'""".*?"""', "", source_of(API), flags=re.S)
    identifiers = {node.id if isinstance(node, ast.Name) else node.attr
                   for node in ast.walk(ast.parse(code)) if isinstance(node, (ast.Name, ast.Attribute))}
    hits = identifiers & set(FORBIDDEN_WRITE_CALLS)
    assert not hits, hits


def test_the_api_imports_no_write_capable_module():
    source = source_of(API)
    for module in FORBIDDEN_MODULE_IMPORTS:
        assert module not in source, module


def test_the_api_only_imports_read_functions_from_markets_repository():
    source = source_of(API)
    match = re.search(r"from app\.v2\.repositories import markets as markets_repo", source)
    assert match, "expected a module-level import, not individual function names, so this stays easy to audit"
    # every markets_repo.<name> call actually used must be a read
    used = set(re.findall(r"markets_repo\.(\w+)", source))
    assert used <= {"get_market", "get_market_by_slug", "list_markets", "count_markets", "get_taxonomy_version",
                    "list_taxonomy_versions", "count_primary_classified_companies"}
    assert not used & {"register_market", "register_taxonomy_version"}


def test_a_mutation_attempt_would_be_caught_by_the_write_scan():
    """Proves the write-scan actually bites on THIS module (not just that it found nothing)."""
    sneaky = source_of(API) + ("\n\ndef _sneaky(engine):\n    from app.v2.db.tables import company_market_classification_table as t\n"
                               "    engine.execute(t.insert())\n")
    assert canonical_writes(sneaky, API) != []


# ---------------- no AI, no network, no provider SDK, no worker framework

def test_the_api_imports_no_ai_provider_or_worker_code():
    for path in (API, SCHEMAS):
        assert scan_source(source_of(path), path) == [], path
        for banned in ("openai", "anthropic", "httpx", "requests", "celery", "app.v2.ai", "app.ai", "app.database"):
            assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}\b", source_of(path), re.M), (path, banned)


def test_the_scanner_bites_on_the_api_module():
    real = source_of(API)
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import adapter\n", API)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", API)
    assert "deterministic-imports-worker-framework" in rules_of(real + "\nimport celery\n", API)


def test_ai_cannot_import_the_capital_api_module():
    for source in ("from app.v2.api import router", "import app.v2.api"):
        assert rules_of(source, AI) & {"ai-imports-disallowed-v2-package"}, source


def test_importing_the_api_module_loads_no_provider_or_worker_code():
    result = run_import_probe(["app.v2.api", "app.v2.api_schemas"], cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    for prefix in ("openai", "anthropic", "tavily", "langchain", "celery", "redis", "app.v2.ai", "app.ai", "app.database", "app.workflows"):
        assert not any(m == prefix or m.startswith(prefix + ".") for m in loaded), prefix


# ---------------- public, no admin surface, closed legacy allowlist

def test_no_auth_dependency_is_declared():
    source = source_of(API)
    for banned in ("RequireAuth", "RequireAdmin", "RequireStartupMember", "app.auth"):
        assert banned not in source


def test_the_legacy_allowlist_admits_only_observability():
    assert DEFAULT_RULES.legacy_import_allowlist == ("app.observability",)


def test_the_whole_tree_is_clean_and_the_api_module_is_scanned():
    result = scan_tree()
    assert result.violations == []
    assert API in result.files_scanned and SCHEMAS in result.files_scanned
