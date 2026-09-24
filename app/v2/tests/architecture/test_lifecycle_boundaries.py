"""
The lifecycle resolution boundary, structurally (Increment 18.7):

  - only the approved private writer touches the canonical lifecycle tables, only promotion imports it
  - the lifecycle candidate repository never writes canonical tables
  - AI (app.v2.ai) can never import the lifecycle resolution package
  - app.v2.lifecycle is a no-network package, like every other resolution package
  - no provider SDK, network, collector, worker, Capital metric or Market Pulse code exists in it
  - earlier boundaries (Company resolution, financing resolution, classification, candidate layers) remain green
"""

import ast
import re

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import REPO_ROOT, extract_imports, module_name_for, scan_source, scan_tree
from app.v2.tests.architecture.canonical_write_scan import canonical_writes
from app.v2.tests.architecture.runtime_probe import run_import_probe

V2 = REPO_ROOT / "app" / "v2"
WRITER = "app/v2/lifecycle/_writes.py"
PROMOTION = "app/v2/lifecycle/promotion.py"
ERRORS = "app/v2/lifecycle/errors.py"
DOMAIN = "app/v2/domain/lifecycle_resolution.py"
CANDIDATE_DOMAIN = "app/v2/domain/lifecycle.py"
REPO = "app/v2/repositories/company_lifecycle.py"
LC_CANDIDATE_REPO = "app/v2/repositories/lifecycle_candidates.py"
EVIDENCE = "app/v2/candidates/lifecycle_evidence.py"
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


# ---------------- only approved modules write the canonical lifecycle tables

def test_the_real_tree_writes_the_canonical_lifecycle_tables_only_from_the_private_writer():
    offenders = {rel: found for rel, src in modules() if (found := canonical_writes(src, rel))}
    assert offenders == {}, offenders
    writer_source = source_of(WRITER)
    assert canonical_writes(writer_source, WRITER) == []
    assert canonical_writes(writer_source, "app/v2/lifecycle/other.py")   # the same code anywhere else IS flagged


@pytest.mark.parametrize("source", [
    "from app.v2.db.tables import company_name_history_table\nconn.execute(company_name_history_table.insert())",
    "from app.v2.db.tables import lifecycle_resolution_decision_table as d\nconn.execute(d.insert().values())",
    "from app.v2.db.tables import company_operating_status_table as s\nconn.execute(s.update().values(status='active'))",
    "from app.v2.db.tables import company_acquisition_table as a\nconn.execute(a.delete())",
    "from sqlalchemy import insert\nfrom app.v2.db.tables import company_successor_relationship_table as t\nconn.execute(insert(t))",
    'conn.execute(text("INSERT INTO v2.company_name_history (company_id, new_name) VALUES (:c, :n)"))',
    'conn.execute(text("UPDATE v2.lifecycle_resolution_decision SET reason_code = NULL"))',
    'conn.execute(text("TRUNCATE v2.company_operating_status CASCADE"))',
])
@pytest.mark.parametrize("path", ["app/v2/repositories/sneaky.py", "app/v2/lifecycle/rules.py", "app/v2/repositories/lifecycle_candidates.py",
                                  "app/v2/candidates/service.py", "app/v2/ai/adapter.py"])
def test_the_write_scan_flags_a_canonical_lifecycle_write_anywhere_but_the_private_writer(source, path):
    assert canonical_writes(source, path), (source, path)
    assert canonical_writes(source, WRITER) == []


def test_the_lifecycle_candidate_repository_never_writes_a_canonical_lifecycle_table():
    assert canonical_writes(source_of(LC_CANDIDATE_REPO), LC_CANDIDATE_REPO) == []


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
            if target == "app.v2.lifecycle._writes" or target.startswith("app.v2.lifecycle._writes."):
                importers.add(module)
    assert importers == {"app.v2.lifecycle.promotion"}
    assert set(DEFAULT_RULES.canonical_writer_importers) >= importers


def test_no_create_attach_split_and_no_generic_merge_or_event_api_exists():
    """Unlike financing (create_event_from_candidate/attach_candidate_to_event) or company resolution
    (create_company_from_candidate/attach_candidate_to_company), a lifecycle candidate never brings a new
    entity into existence -- there is no create/attach split and no separate canonical "event" identity, only
    accept/reject/defer on facts about an already-canonical company. Scoped to the lifecycle package itself,
    never the whole tree: financing/company resolution legitimately have their own create/attach verbs."""
    banned = re.compile(r"^(create|attach|merge)_?(lifecycle_?)?(event|company)")
    defs = {}
    for rel, src in modules(V2 / "lifecycle"):
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and banned.search(node.name):
                defs.setdefault(rel, []).append(node.name)
    assert defs == {}


# ---------------- AI may propose, never decide, promote, merge, or verify a lifecycle fact

@pytest.mark.parametrize("source", [
    "from app.v2.lifecycle import promotion", "from app.v2.lifecycle.promotion import accept_lifecycle_event",
    "import app.v2.lifecycle.promotion", "from app.v2.lifecycle._writes import insert_name_change",
    "from app.v2.lifecycle import _writes", "from app.v2.repositories.company_lifecycle import get_company_lifecycle_state",
    "from app.v2.repositories import company_lifecycle",
])
def test_ai_cannot_import_the_lifecycle_promotion_boundary(source):
    assert rules_of(source, AI) & {"ai-imports-disallowed-v2-package", "ai-imports-persistence"}, source


def test_ai_may_see_the_pure_lifecycle_resolution_vocabulary_but_not_the_writer():
    assert rules_of("from app.v2.domain.lifecycle_resolution import LifecycleFactSelection", AI) == set()
    assert rules_of("from app.v2.domain.lifecycle_resolution import LifecycleDecisionKind", AI) == set()
    assert rules_of("from app.v2.domain.lifecycle import OperatingStatus", AI) == set()


@pytest.mark.parametrize("path", ["app/v2/candidates/proposer.py", "app/v2/candidates/evidence.py", "app/v2/candidates/lifecycle_evidence.py",
                                  "app/v2/repositories/lifecycle_candidates.py"])
@pytest.mark.parametrize("source", ["from app.v2.lifecycle import promotion", "from app.v2.lifecycle.promotion import reject_candidate",
                                    "import app.v2.lifecycle._writes", "from app.v2.repositories.company_lifecycle import get_company_lifecycle_state"])
def test_the_candidate_layer_cannot_reach_lifecycle_promotion(source, path):
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


def test_no_lifecycle_code_names_confidence_ai_or_a_knowledge_graph():
    forbidden = {"confidence", "score", "probability", "openai", "anthropic", "llm", "gpt", "prompt", "embedding",
                "similarity", "fuzzy", "levenshtein", "knowledgegraph", "entitygraph"}
    for path in (DOMAIN, CANDIDATE_DOMAIN, WRITER, PROMOTION, ERRORS, REPO, EVIDENCE):
        names = {n for n in _identifiers(path) if forbidden & set(re.sub(r"([a-z])([A-Z])", r"\1_\2", n).lower().split("_"))}
        assert not names, (path, names)


def test_the_lifecycle_package_imports_no_provider_network_worker_or_legacy_code():
    for rel, src in modules():
        if rel.startswith("app/v2/lifecycle/") or rel == REPO:
            assert scan_source(src, rel) == [], rel
            for banned in ("openai", "anthropic", "httpx", "requests", "socket", "celery", "app.ai", "app.api", "app.database", "app.v2.ai"):
                assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}\b", src, re.M), (rel, banned)


def test_the_scanner_bites_on_the_lifecycle_promotion_module():
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
    for path in (DOMAIN, CANDIDATE_DOMAIN, WRITER, PROMOTION, ERRORS, REPO, EVIDENCE, LC_CANDIDATE_REPO):
        assert path in result.files_scanned


def test_importing_the_lifecycle_modules_loads_no_provider_network_or_legacy_code():
    names = ["app.v2.domain.lifecycle", "app.v2.domain.lifecycle_resolution", "app.v2.lifecycle.promotion",
             "app.v2.lifecycle._writes", "app.v2.lifecycle.errors", "app.v2.repositories.company_lifecycle",
             "app.v2.repositories.lifecycle_candidates", "app.v2.candidates.lifecycle_evidence"]
    result = run_import_probe(names, cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    for prefix in ("openai", "anthropic", "tavily", "langchain", "requests", "httpx", "aiohttp", "urllib3", "celery", "redis",
                   "app.v2.ai", "app.api", "app.ai", "app.database", "app.models", "app.workflows"):
        assert not any(m == prefix or m.startswith(prefix + ".") for m in loaded), prefix


def test_the_pure_lifecycle_domains_stay_pure():
    for domain_module, domain_path in (("app.v2.domain.lifecycle", CANDIDATE_DOMAIN), ("app.v2.domain.lifecycle_resolution", DOMAIN)):
        assert scan_source(source_of(domain_path), domain_path) == []
        result = run_import_probe([domain_module], cwd=REPO_ROOT)
        loaded = set(result.loaded)
        assert not any(m == "sqlalchemy" or m.startswith(("sqlalchemy.", "app.v2.repositories", "app.v2.db")) for m in loaded)


def test_the_pure_lifecycle_evidence_module_stays_pure():
    assert scan_source(source_of(EVIDENCE), EVIDENCE) == []
    result = run_import_probe(["app.v2.candidates.lifecycle_evidence"], cwd=REPO_ROOT)
    loaded = set(result.loaded)
    assert not any(m == "sqlalchemy" or m.startswith(("sqlalchemy.", "app.v2.repositories", "app.v2.db")) for m in loaded)
