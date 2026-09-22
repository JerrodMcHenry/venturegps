"""
The financing resolution boundary, structurally (Increment 11):

  - only the approved private writer touches the canonical financing tables, only promotion imports it
  - the financing candidate repository never writes canonical tables
  - AI (app.v2.ai) can never import the financing resolution package
  - no provider SDK, network, collector, worker, Capital metric or Market Pulse code exists
  - earlier boundaries (Company resolution, candidate layers) remain green
"""

import ast
import re

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import REPO_ROOT, extract_imports, module_name_for, scan_source, scan_tree
from app.v2.tests.architecture.canonical_write_scan import canonical_writes
from app.v2.tests.architecture.runtime_probe import run_import_probe

V2 = REPO_ROOT / "app" / "v2"
WRITER = "app/v2/financing_resolution/_writes.py"
PROMOTION = "app/v2/financing_resolution/promotion.py"
ERRORS = "app/v2/financing_resolution/errors.py"
DOMAIN = "app/v2/domain/financing_resolution.py"
REPO = "app/v2/repositories/financing_events.py"
FIN_CANDIDATE_REPO = "app/v2/repositories/financing_event_candidates.py"
AI = "app/v2/ai/adapter.py"


def modules(root=V2):
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        yield rel, path.read_text()


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


def source_of(path):
    return (REPO_ROOT / path).read_text()


# ---------------- only approved modules write the canonical financing tables

def test_the_real_tree_writes_the_canonical_financing_tables_only_from_the_private_writer():
    offenders = {rel: found for rel, src in modules() if (found := canonical_writes(src, rel))}
    assert offenders == {}, offenders
    writer_source = source_of(WRITER)
    assert canonical_writes(writer_source, WRITER) == []
    assert canonical_writes(writer_source, "app/v2/financing_resolution/other.py")   # the same code anywhere else IS flagged


@pytest.mark.parametrize("source", [
    "from app.v2.db.tables import financing_event_table\nconn.execute(financing_event_table.insert())",
    "from app.v2.db.tables import financing_resolution_decision_table as d\nconn.execute(d.insert().values())",
    "from app.v2.db.tables import financing_event_stage_table\nconn.execute(financing_event_stage_table.update().values(stage='seed'))",
    "from app.v2.db.tables import financing_event_verified_round_amount_table as a\nconn.execute(a.delete())",
    "from sqlalchemy import insert\nfrom app.v2.db.tables import financing_event_date_table as d\nconn.execute(insert(d))",
    'conn.execute(text("INSERT INTO v2.financing_event (company_id) VALUES (:c)"))',
    'conn.execute(text("UPDATE v2.financing_resolution_decision SET reason_code = NULL"))',
    'conn.execute(text("TRUNCATE v2.financing_event_type CASCADE"))',
])
@pytest.mark.parametrize("path", ["app/v2/repositories/sneaky.py", "app/v2/financing_resolution/rules.py", "app/v2/repositories/financing_event_candidates.py",
                                  "app/v2/candidates/service.py", "app/v2/ai/adapter.py"])
def test_the_write_scan_flags_a_canonical_financing_write_anywhere_but_the_private_writer(source, path):
    assert canonical_writes(source, path), (source, path)
    assert canonical_writes(source, WRITER) == []


def test_the_financing_candidate_repository_never_writes_a_canonical_financing_table():
    assert canonical_writes(source_of(FIN_CANDIDATE_REPO), FIN_CANDIDATE_REPO) == []


def test_the_read_repository_never_writes():
    source = source_of(REPO)
    code = re.sub(r'""".*?"""', "", source, flags=re.S)
    assert not re.search(r"\.(insert|update|delete)\(|\binsert\(|\bupdate\(|\bdelete\(|pg_insert", code)
    assert "_writes" not in code and "promotion" not in code


def test_only_promotion_imports_the_private_writer():
    importers = set()
    for rel, src in modules():
        module, is_package = module_name_for(rel)
        for ref in extract_imports(ast.parse(src), module, is_package):
            target = ref.name or ""
            if target == "app.v2.financing_resolution._writes" or target.startswith("app.v2.financing_resolution._writes."):
                importers.add(module)
    assert importers == {"app.v2.financing_resolution.promotion"}
    assert set(DEFAULT_RULES.canonical_writer_importers) >= importers


def test_no_generic_public_create_financing_event_api_exists():
    verb_event = re.compile(r"^(create|insert|add|save|upsert|write)_?(financing_?)?event(?!_candidate)")
    defs = {}
    for rel, src in modules():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and verb_event.search(node.name):
                defs.setdefault(rel, []).append(node.name)
    assert defs == {WRITER: ["insert_event"], PROMOTION: ["create_event_from_candidate"]}


# ---------------- AI may propose, never decide, promote, merge, or verify an amount

@pytest.mark.parametrize("source", [
    "from app.v2.financing_resolution import promotion", "from app.v2.financing_resolution.promotion import create_event_from_candidate",
    "import app.v2.financing_resolution.promotion", "from app.v2.financing_resolution._writes import insert_event",
    "from app.v2.financing_resolution import _writes", "from app.v2.repositories.financing_events import get_financing_event",
    "from app.v2.repositories import financing_events",
])
def test_ai_cannot_import_the_financing_promotion_boundary(source):
    assert rules_of(source, AI) & {"ai-imports-disallowed-v2-package", "ai-imports-persistence"}, source


def test_ai_may_see_the_pure_financing_resolution_vocabulary_but_not_the_writer():
    assert rules_of("from app.v2.domain.financing_resolution import FactSelection", AI) == set()
    assert rules_of("from app.v2.domain.financing_resolution import FinancingDecisionKind", AI) == set()


@pytest.mark.parametrize("path", ["app/v2/candidates/proposer.py", "app/v2/candidates/evidence.py", "app/v2/candidates/financing_evidence.py",
                                  "app/v2/repositories/financing_event_candidates.py", "app/v2/candidates/financing_extractor.py"])
@pytest.mark.parametrize("source", ["from app.v2.financing_resolution import promotion", "from app.v2.financing_resolution.promotion import reject_candidate",
                                    "import app.v2.financing_resolution._writes", "from app.v2.repositories.financing_events import get_financing_event"])
def test_the_candidate_layer_cannot_reach_financing_promotion(source, path):
    assert "candidate-layer-imports-canonical" in rules_of(source, path)


# ---------------- nothing here is probabilistic, provider-aware, or a merge

def _identifiers(path):
    tree = ast.parse(source_of(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name


@pytest.mark.parametrize("path", (DOMAIN, WRITER, PROMOTION, ERRORS, REPO))
def test_no_financing_resolution_code_names_confidence_ai_or_merge(path):
    forbidden = {"confidence", "score", "probability", "openai", "anthropic", "llm", "gpt", "prompt", "embedding",
                 "similarity", "fuzzy", "levenshtein", "merge", "mergefinancing", "financingeventmerge"}
    names = {n for n in _identifiers(path) if forbidden & set(re.sub(r"([a-z])([A-Z])", r"\1_\2", n).lower().split("_"))}
    assert not names, (path, names)


def test_the_financing_resolution_package_imports_no_provider_network_worker_or_legacy_code():
    for rel, src in modules():
        if rel.startswith("app/v2/financing_resolution/") or rel == REPO:
            assert scan_source(src, rel) == [], rel
            for banned in ("openai", "anthropic", "httpx", "requests", "socket", "celery", "app.ai", "app.api", "app.database", "app.v2.ai"):
                assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}\b", src, re.M), (rel, banned)


def test_the_scanner_bites_on_the_financing_promotion_module():
    real = source_of(PROMOTION)
    assert scan_source(real, PROMOTION) == []
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import adapter\n", PROMOTION)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport anthropic\n", PROMOTION)
    assert "network-import-forbidden" in rules_of(real + "\nimport httpx\n", PROMOTION)
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "TAVILY_API_KEY"\n', PROMOTION)
    assert "deterministic-imports-worker-framework" in rules_of(real + "\nimport celery\n", PROMOTION)


def test_no_capital_metric_signal_or_market_pulse_code_exists():
    for name in ("capital", "signals", "market_pulse", "metrics", "radar"):
        assert not (V2 / name).exists(), name


# ---------------- runtime and whole tree

def test_the_whole_tree_is_clean_and_the_new_modules_are_scanned():
    result = scan_tree()
    assert result.violations == []
    for path in (DOMAIN, WRITER, PROMOTION, ERRORS, REPO):
        assert path in result.files_scanned


def test_importing_the_financing_resolution_modules_loads_no_provider_network_or_legacy_code():
    names = ["app.v2.domain.financing_resolution", "app.v2.financing_resolution.promotion", "app.v2.financing_resolution._writes",
             "app.v2.financing_resolution.errors", "app.v2.repositories.financing_events"]
    result = run_import_probe(names, cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    for prefix in ("openai", "anthropic", "tavily", "langchain", "requests", "httpx", "aiohttp", "urllib3", "celery", "redis",
                   "app.v2.ai", "app.api", "app.ai", "app.database", "app.models", "app.workflows"):
        assert not any(m == prefix or m.startswith(prefix + ".") for m in loaded), prefix


def test_the_pure_financing_resolution_domain_stays_pure():
    assert scan_source(source_of(DOMAIN), DOMAIN) == []
    result = run_import_probe(["app.v2.domain.financing_resolution"], cwd=REPO_ROOT)
    loaded = set(result.loaded)
    assert not any(m == "sqlalchemy" or m.startswith(("sqlalchemy.", "app.v2.repositories", "app.v2.db")) for m in loaded)
