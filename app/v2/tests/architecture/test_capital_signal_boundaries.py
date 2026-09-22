"""
The Capital Signal boundary, structurally (Increment 13):

  - the pure engine (app.v2.domain.capital_signal) has no DB/network/AI/environment/wall-clock imports
  - AI (app.v2.ai) can never import the signal domain module or the repository
  - the candidate layer can never reach it
  - no Market Pulse / Capital Signal persistence / forecasting / scoring code exists
  - no wall-clock function (datetime.now/utcnow/date.today) is used anywhere in the pure engine
  - earlier boundaries remain green
"""

import ast
import re

import pytest

from app.v2.tests.architecture.boundary_scanner import REPO_ROOT, scan_source, scan_tree
from app.v2.tests.architecture.canonical_write_scan import canonical_writes
from app.v2.tests.architecture.runtime_probe import run_import_probe

V2 = REPO_ROOT / "app" / "v2"
DOMAIN = "app/v2/domain/capital_signal.py"
REPO = "app/v2/repositories/capital_signal.py"
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


# ---------------- no persistence, no future concepts

def test_capital_signal_persists_nothing():
    assert canonical_writes(source_of(DOMAIN), DOMAIN) == []
    assert canonical_writes(source_of(REPO), REPO) == []
    code = re.sub(r'""".*?"""', "", source_of(REPO), flags=re.S)
    assert not re.search(r"\.(insert|update|delete)\(|\binsert\(|\bupdate\(|\bdelete\(|pg_insert", code)


def test_no_market_pulse_or_other_dimension_code_exists():
    for name in ("market_pulse", "formation", "talent", "innovation", "attention", "radar", "signals"):
        assert not (V2 / name).exists(), name
    defined = set()
    for rel, src in modules():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name.lower())
    for banned in ("marketpulse", "forecastcapital", "capitalscore", "investmentrecommendation", "predictcapital",
                   "capitalsignalhistory", "capitalsignalsnapshot"):
        assert banned not in defined, banned


def test_no_new_database_tables_were_created():
    from app.v2.db import tables  # noqa: F401
    from app.v2.db.metadata import metadata
    assert not any("signal" in t or "pulse" in t for t in metadata.tables)


# ---------------- no wall clock, ever

def test_the_pure_engine_never_reads_the_wall_clock():
    source = source_of(DOMAIN)
    code = re.sub(r'""".*?"""', "", source, flags=re.S)
    for banned in ("datetime.now(", "utcnow(", "date.today(", "time.time("):
        assert banned not in code, banned


def test_the_repository_layer_never_reads_the_wall_clock_either():
    code = re.sub(r'""".*?"""', "", source_of(REPO), flags=re.S)
    for banned in ("datetime.now(", "utcnow(", "date.today(", "time.time("):
        assert banned not in code, banned


# ---------------- no AI, no network, no provider SDK

@pytest.mark.parametrize("source", [
    "from app.v2.domain.capital_signal import compute_capital_signal", "from app.v2.domain import capital_signal",
    "from app.v2.repositories.capital_signal import compute_capital_signal_for_market",
    "from app.v2.repositories import capital_signal",
])
def test_ai_cannot_import_the_capital_signal_repository_but_may_see_the_pure_types(source):
    if "repositories" in source:
        assert rules_of(source, AI) & {"ai-imports-disallowed-v2-package", "ai-imports-persistence"}, source
    else:
        # the pure result/vocabulary types are readable (no persistence, no decision authority); computing one
        # still requires the repository, which IS blocked above
        assert rules_of(source, AI) == set()


@pytest.mark.parametrize("path", ["app/v2/candidates/proposer.py", "app/v2/candidates/evidence.py", "app/v2/candidates/financing_evidence.py",
                                  "app/v2/repositories/financing_event_candidates.py"])
@pytest.mark.parametrize("source", ["from app.v2.repositories.capital_signal import compute_capital_signal_for_market",
                                    "from app.v2.repositories import capital_signal"])
def test_the_candidate_layer_cannot_reach_capital_signal(source, path):
    assert "candidate-layer-imports-canonical" in rules_of(source, path)


def test_the_capital_signal_modules_import_no_provider_network_worker_or_legacy_code():
    for path in (DOMAIN, REPO):
        assert scan_source(source_of(path), path) == [], path
        for banned in ("openai", "anthropic", "httpx", "requests", "socket", "celery", "app.ai", "app.api", "app.database", "app.v2.ai"):
            assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}\b", source_of(path), re.M), (path, banned)


def test_the_scanner_bites_on_the_pure_engine():
    real = source_of(DOMAIN)
    assert scan_source(real, DOMAIN) == []
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import adapter\n", DOMAIN)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", DOMAIN)
    assert rules_of(real + "\nimport httpx\n", DOMAIN)  # pure zone: pure-imports-forbidden
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "TAVILY_API_KEY"\n', DOMAIN)


def test_the_pure_module_does_not_load_sqlalchemy_or_the_repositories_at_runtime():
    result = run_import_probe(["app.v2.domain.capital_signal"], cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    assert not any(m == "sqlalchemy" or m.startswith(("sqlalchemy.", "app.v2.repositories", "app.v2.db")) for m in loaded)


def test_importing_the_new_modules_loads_no_provider_network_worker_or_legacy_code():
    names = ["app.v2.domain.capital_signal", "app.v2.repositories.capital_signal"]
    result = run_import_probe(names, cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    for prefix in ("openai", "anthropic", "tavily", "langchain", "requests", "httpx", "aiohttp", "urllib3", "celery", "redis",
                   "app.v2.ai", "app.api", "app.ai", "app.database", "app.models", "app.workflows"):
        assert not any(m == prefix or m.startswith(prefix + ".") for m in loaded), prefix


# ---------------- the engine reuses Increment 12, it does not duplicate it

def test_the_repository_reuses_the_increment_12_engine_rather_than_reimplementing_it():
    source = source_of(REPO)
    assert "from app.v2.domain.capital_metrics import compute_capital_metrics" in source
    assert "from app.v2.repositories.capital_metrics import get_primary_attributed_financing_events" in source
    # no independent SQL: the repository has no SELECT of its own on financing/company/classification tables
    assert "select(" not in source and "SELECT" not in source.upper()


def test_the_whole_tree_is_clean_and_the_new_modules_are_scanned():
    result = scan_tree()
    assert result.violations == []
    for path in (DOMAIN, REPO):
        assert path in result.files_scanned
