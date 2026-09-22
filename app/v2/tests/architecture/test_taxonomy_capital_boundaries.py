"""
The taxonomy/classification/Capital-metrics boundary, structurally (Increment 12):

  - only the approved private writer touches v2.company_market_classification; only service.py imports it
  - Market/TaxonomyVersion registration (a plain repository, like Source) is NOT authority-gated -- documented
  - AI (app.v2.ai) can never import the classification package or the classification/markets/capital-metrics repos
  - the candidate layer can never reach classification, markets or capital metrics
  - the Capital metric engine (app.v2.domain.capital_metrics) is pure: no DB, no network, no AI, no environment
  - no collector, worker, scheduler, Capital Signal or Market Pulse code exists
  - earlier boundaries remain green
"""

import ast
import re

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import REPO_ROOT, extract_imports, module_name_for, scan_source, scan_tree
from app.v2.tests.architecture.canonical_write_scan import canonical_writes
from app.v2.tests.architecture.runtime_probe import run_import_probe

V2 = REPO_ROOT / "app" / "v2"
WRITER = "app/v2/classification/_writes.py"
SERVICE = "app/v2/classification/service.py"
ERRORS = "app/v2/classification/errors.py"
TAXONOMY_DOMAIN = "app/v2/domain/taxonomy.py"
CAPITAL_DOMAIN = "app/v2/domain/capital_metrics.py"
MARKETS_REPO = "app/v2/repositories/markets.py"
CAPITAL_REPO = "app/v2/repositories/capital_metrics.py"
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


# ---------------- no product-layer overreach

def test_no_capital_signal_market_pulse_or_radar_code_exists():
    for name in ("capital", "signals", "market_pulse", "metrics", "radar", "collectors", "workers", "scheduler"):
        assert not (V2 / name).exists(), name


def test_no_taxonomy_editor_or_market_discovery_code_exists():
    defined = set()
    for rel, src in modules():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name.lower())
    for banned in ("classifymarketai", "discovermarket", "suggestmarket", "marketembedding", "marketsimilarity",
                   "forecastcapital", "capitalsignal", "marketpulse"):
        assert banned not in defined, banned


# ---------------- only the approved writer touches classification

def test_the_real_tree_writes_company_market_classification_only_from_the_private_writer():
    offenders = {rel: found for rel, src in modules() if (found := canonical_writes(src, rel))}
    assert offenders == {}, offenders
    writer_source = source_of(WRITER)
    assert canonical_writes(writer_source, WRITER) == []
    assert canonical_writes(writer_source, "app/v2/classification/other.py")


@pytest.mark.parametrize("source", [
    "from app.v2.db.tables import company_market_classification_table as t\nconn.execute(t.insert())",
    "from sqlalchemy import insert\nfrom app.v2.db.tables import company_market_classification_table as t\nconn.execute(insert(t))",
    'conn.execute(text("INSERT INTO v2.company_market_classification (company_id) VALUES (:c)"))',
    'conn.execute(text("UPDATE v2.company_market_classification SET role = \'primary\'"))',
])
@pytest.mark.parametrize("path", ["app/v2/repositories/sneaky.py", "app/v2/repositories/markets.py", "app/v2/repositories/capital_metrics.py", "app/v2/ai/adapter.py"])
def test_the_write_scan_flags_a_classification_write_anywhere_but_the_private_writer(source, path):
    assert canonical_writes(source, path), (source, path)
    assert canonical_writes(source, WRITER) == []


def test_only_service_imports_the_private_writer():
    importers = set()
    for rel, src in modules():
        module, is_package = module_name_for(rel)
        for ref in extract_imports(ast.parse(src), module, is_package):
            target = ref.name or ""
            if target == "app.v2.classification._writes" or target.startswith("app.v2.classification._writes."):
                importers.add(module)
    assert importers == {"app.v2.classification.service"}


def test_the_markets_and_capital_metrics_repositories_never_write_classification():
    for path in (MARKETS_REPO, CAPITAL_REPO):
        assert canonical_writes(source_of(path), path) == []
    code = re.sub(r'""".*?"""', "", source_of(CAPITAL_REPO), flags=re.S)
    assert not re.search(r"\.(insert|update|delete)\(|\binsert\(|\bupdate\(|\bdelete\(|pg_insert", code)


def test_market_and_taxonomy_version_registration_is_deliberately_not_authority_gated():
    """Documents the design choice: Market/TaxonomyVersion are taxonomy DEFINITIONS (like Source), not
    evidence-derived truth, so they are registered directly and are not in the canonical writer registry."""
    assert "market_table" not in DEFAULT_RULES.canonical_table_variables
    assert "taxonomy_version_table" not in DEFAULT_RULES.canonical_table_variables
    assert "company_market_classification_table" in DEFAULT_RULES.canonical_table_variables


# ---------------- AI cannot decide or write classification

@pytest.mark.parametrize("source", [
    "from app.v2.classification import service", "from app.v2.classification.service import classify_company",
    "import app.v2.classification.service", "from app.v2.classification._writes import insert_classification",
    "from app.v2.classification import _writes", "from app.v2.repositories.markets import register_market",
    "from app.v2.repositories.capital_metrics import compute_capital_metrics_for_market",
    "from app.v2.repositories import markets", "from app.v2.repositories import capital_metrics",
])
def test_ai_cannot_import_classification_markets_or_capital_metrics_persistence(source):
    assert rules_of(source, AI) & {"ai-imports-disallowed-v2-package", "ai-imports-persistence"}, source


def test_ai_may_see_the_pure_taxonomy_and_capital_vocabulary_but_not_the_writer():
    assert rules_of("from app.v2.domain.taxonomy import ClassificationRole", AI) == set()
    assert rules_of("from app.v2.domain.capital_metrics import CapitalEventInput", AI) == set()


@pytest.mark.parametrize("path", ["app/v2/candidates/proposer.py", "app/v2/candidates/evidence.py", "app/v2/candidates/financing_evidence.py",
                                  "app/v2/repositories/financing_event_candidates.py", "app/v2/candidates/new_extractor.py"])
@pytest.mark.parametrize("source", ["from app.v2.classification import service", "from app.v2.classification.service import classify_company",
                                    "import app.v2.classification._writes", "from app.v2.repositories.markets import register_market",
                                    "from app.v2.repositories.capital_metrics import compute_capital_metrics_for_market"])
def test_the_candidate_layer_cannot_reach_classification_markets_or_capital_metrics(source, path):
    assert "candidate-layer-imports-canonical" in rules_of(source, path)


# ---------------- purity of the Capital metric engine

def test_no_score_signal_or_double_counting_surface_exists():
    forbidden = {"score", "signal", "trend", "forecast", "increase", "decrease"}
    for rel, src in modules():
        if rel != CAPITAL_DOMAIN:
            continue
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
        lowered = {re.sub(r"([a-z])([A-Z])", r"\1_\2", n).lower() for n in names}
        hits = {w for w in forbidden if any(w in n.split("_") for n in lowered)}
        assert not hits, (rel, hits)


def test_the_capital_metric_engine_imports_no_db_network_worker_or_ai():
    for path in (TAXONOMY_DOMAIN, CAPITAL_DOMAIN):
        assert scan_source(source_of(path), path) == [], path
        for banned in ("openai", "anthropic", "httpx", "requests", "socket", "celery", "app.ai", "app.api", "app.database", "app.v2.ai",
                       "app.v2.db", "app.v2.repositories"):
            assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}\b", source_of(path), re.M), (path, banned)


def test_the_scanner_bites_on_the_capital_metric_engine():
    real = source_of(CAPITAL_DOMAIN)
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import adapter\n", CAPITAL_DOMAIN)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", CAPITAL_DOMAIN)
    assert rules_of(real + "\nimport httpx\n", CAPITAL_DOMAIN)   # the pure zone forbids it (pure-imports-forbidden)
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "TAVILY_API_KEY"\n', CAPITAL_DOMAIN)


def test_the_pure_modules_do_not_load_sqlalchemy_or_the_repositories_at_runtime():
    result = run_import_probe(["app.v2.domain.taxonomy", "app.v2.domain.capital_metrics"], cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    assert not any(m == "sqlalchemy" or m.startswith(("sqlalchemy.", "app.v2.repositories", "app.v2.db")) for m in loaded)


def test_the_classification_and_capital_repository_packages_import_no_provider_network_or_legacy_code():
    for rel, src in modules():
        if rel in (WRITER, SERVICE, ERRORS, MARKETS_REPO, CAPITAL_REPO, TAXONOMY_DOMAIN, CAPITAL_DOMAIN):
            assert scan_source(src, rel) == [], rel
            for banned in ("openai", "anthropic", "httpx", "requests", "socket", "celery", "app.ai", "app.api", "app.database", "app.v2.ai"):
                assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}\b", src, re.M), (rel, banned)


def test_importing_the_new_modules_loads_no_provider_network_worker_or_legacy_code():
    names = ["app.v2.domain.taxonomy", "app.v2.domain.capital_metrics", "app.v2.repositories.markets",
             "app.v2.repositories.capital_metrics", "app.v2.classification.service", "app.v2.classification._writes"]
    result = run_import_probe(names, cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    for prefix in ("openai", "anthropic", "tavily", "langchain", "requests", "httpx", "aiohttp", "urllib3", "celery", "redis",
                   "app.v2.ai", "app.api", "app.ai", "app.database", "app.models", "app.workflows"):
        assert not any(m == prefix or m.startswith(prefix + ".") for m in loaded), prefix


# ---------------- runtime and whole tree

def test_the_whole_tree_is_clean_and_the_new_modules_are_scanned():
    result = scan_tree()
    assert result.violations == []
    for path in (WRITER, SERVICE, ERRORS, TAXONOMY_DOMAIN, CAPITAL_DOMAIN, MARKETS_REPO, CAPITAL_REPO):
        assert path in result.files_scanned
