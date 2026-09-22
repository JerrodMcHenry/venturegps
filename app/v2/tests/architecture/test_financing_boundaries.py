"""
The financing-candidate layer, structurally (Increment 10, CAPITAL):

  - candidates are UNTRUSTED proposals: no canonical FinancingEvent table, promotion or resolution exists
  - no AI, provider SDK, network, collector, worker, scheduler, metric, signal or Market Pulse code
  - money is never a float; there is no verified/generic/funding amount and no generic event_date
  - the financing repository writes only its own three tables and never canonical company/resolution tables
  - earlier boundaries (candidate layer cannot promote, AI cannot persist) still hold for the new modules
"""

import ast
import re

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import REPO_ROOT, scan_source, scan_tree
from app.v2.tests.architecture.canonical_write_scan import canonical_writes
from app.v2.tests.architecture.runtime_probe import run_import_probe

V2 = REPO_ROOT / "app" / "v2"
DOMAIN = "app/v2/domain/financing.py"
EVIDENCE = "app/v2/candidates/financing_evidence.py"
REPO = "app/v2/repositories/financing_event_candidates.py"
FILES = (DOMAIN, EVIDENCE, REPO)


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


def source_of(path):
    return (REPO_ROOT / path).read_text()


def identifiers(path):
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


# ---------------- nothing canonical, nothing beyond the candidate model

def test_no_canonical_financing_event_promotion_resolution_or_capital_code_exists():
    for name in ("financing", "capital", "signals", "market", "market_pulse", "metrics", "collectors", "workers", "scheduler", "radar", "attribution"):
        assert not (V2 / name).exists(), name
    defined = set()
    for path in V2.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name.lower())
    for banned in ("promote_financing_event", "resolve_financing_event", "create_financing_event", "financingevent", "storedfinancingevent",
                   "calculate_capital", "capital_signal", "market_pulse", "capital_metric"):
        assert banned not in defined, banned
    assert not any(re.search(r"financing_?event(?!_?candidate)", n) for n in defined if "candidate" not in n and "proposed" not in n), defined


def test_the_canonical_table_variables_do_not_include_any_financing_table():
    assert not any("financing" in name for name in DEFAULT_RULES.canonical_table_variables + DEFAULT_RULES.canonical_table_names)


def test_the_metadata_has_only_candidate_financing_tables():
    from app.v2.db import tables  # noqa: F401
    from app.v2.db.metadata import metadata
    financing = sorted(t for t in metadata.tables if "financing" in t)
    assert financing == ["v2.financing_event_candidate", "v2.financing_event_candidate_amount", "v2.financing_event_candidate_date"]


# ---------------- names that would imply truth or collapse semantics

@pytest.mark.parametrize("path", FILES)
def test_no_module_names_funding_verified_or_generic_amounts_dates_or_metrics(path):
    for name in set(identifiers(path)):
        lowered = name.lower()
        for banned in ("funding_amount", "verified_round", "verified_amount", "event_date", "market_pulse", "capital_signal", "capital_metric",
                       "confidence", "openai", "anthropic", "prompt", "exchange_rate", "fx_", "convert_currency"):
            assert banned not in lowered, (path, name)
        assert lowered not in {"funding", "round_amount"}, (path, name)       # (a local named `amount` is fine; the FIELD is tested elsewhere)


@pytest.mark.parametrize("path", (DOMAIN, REPO))
def test_money_is_never_a_float_in_the_financing_modules(path):
    tree = ast.parse(source_of(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "float":
            # allowed only as the NEGATIVE check in Money.from_decimal (isinstance(amount, (float, bool)) -> refuse)
            assert path == DOMAIN
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            pytest.fail(f"float literal in {path}")
    domain_floats = [n for n in ast.walk(ast.parse(source_of(DOMAIN))) if isinstance(n, ast.Name) and n.id == "float"]
    assert len(domain_floats) == 1                                                  # only the refusal


# ---------------- purity and determinism

@pytest.mark.parametrize("path", FILES)
def test_the_financing_modules_pass_every_existing_boundary_rule(path):
    assert scan_source(source_of(path), path) == []


@pytest.mark.parametrize("path", (DOMAIN, EVIDENCE))
def test_the_domain_and_evidence_modules_are_pure_zone_members(path):
    real = source_of(path)
    assert rules_of(real + "\nimport sqlalchemy\n", path)
    assert rules_of(real + "\nimport os\n", path)
    assert rules_of(real + "\nfrom app.v2.repositories import sources\n", path)
    assert rules_of(real + "\nimport httpx\n", path)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", path)


@pytest.mark.parametrize("path", (REPO,))
def test_the_repository_bites_on_ai_network_worker_and_env_imports(path):
    real = source_of(path)
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import x\n", path)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport anthropic\n", path)
    assert "network-import-forbidden" in rules_of(real + "\nimport requests\n", path)
    assert "deterministic-imports-worker-framework" in rules_of(real + "\nimport celery\n", path)
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "TAVILY_API_KEY"\n', path)


def test_the_candidate_layer_rule_covers_the_financing_repository_and_it_cannot_reach_resolution():
    assert "app.v2.repositories.financing_event_candidates" in DEFAULT_RULES.candidate_layer_packages
    for source in ("from app.v2.resolution import promotion", "from app.v2.resolution.rules import resolve_by_exact_identifier",
                   "from app.v2.repositories.companies import get_company"):
        assert "candidate-layer-imports-canonical" in rules_of(source, REPO), source
        assert "candidate-layer-imports-canonical" in rules_of(source, "app/v2/candidates/financing_service.py"), source


def test_ai_cannot_import_the_financing_persistence_or_evidence_internals():
    for source in ("from app.v2.repositories.financing_event_candidates import persist_financing_event_candidates",
                   "from app.v2.repositories import financing_event_candidates",
                   "from app.v2.db.tables import financing_event_candidate_table",
                   "from app.v2.candidates.financing_evidence import verify_financing_proposal"):
        assert rules_of(source, "app/v2/ai/adapter.py") & {"ai-imports-persistence", "ai-imports-disallowed-v2-package"}, source
    assert rules_of("from app.v2.domain.financing import FinancingEventCandidateProposal", "app/v2/ai/adapter.py") == set()   # the pure proposal type is the port


# ---------------- writes

def test_the_financing_repository_writes_only_its_three_tables_and_no_canonical_tables():
    source = source_of(REPO)
    inserted = set(re.findall(r"(?:pg_)?insert\((\w+)\)", source))
    assert inserted == {"fa", "fd", "fc"}
    imported = set(re.findall(r"import (\w+_table)\b", source))
    assert imported == {"company_table", "financing_event_candidate_amount_table", "financing_event_candidate_date_table",
                        "financing_event_candidate_table", "processing_attempt_table"}
    assert canonical_writes(source, REPO) == []                          # a company READ (FOR KEY SHARE) is not a canonical write
    assert not re.search(r"\b(update|delete)\(", re.sub(r'""".*?"""', "", source, flags=re.S))


def test_the_only_canonical_writer_is_unchanged_and_no_financing_module_touches_it():
    for path in FILES:
        assert canonical_writes(source_of(path), path) == []
        assert "_writes" not in source_of(path) and "promotion" not in re.sub(r'""".*?"""', "", source_of(path), flags=re.S)


# ---------------- runtime and whole tree

def test_the_whole_tree_is_clean_and_the_new_modules_are_scanned():
    result = scan_tree()
    assert result.violations == []
    for path in FILES:
        assert path in result.files_scanned


def test_importing_the_financing_modules_loads_no_provider_network_worker_or_legacy_code():
    names = ["app.v2.domain.financing", "app.v2.candidates.financing_evidence", "app.v2.repositories.financing_event_candidates"]
    result = run_import_probe(names, cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    for prefix in ("openai", "anthropic", "tavily", "langchain", "requests", "httpx", "aiohttp", "urllib3", "celery", "redis", "apscheduler",
                   "app.v2.ai", "app.v2.resolution", "app.api", "app.ai", "app.database", "app.models", "app.workflows"):
        assert not any(m == prefix or m.startswith(prefix + ".") for m in loaded), prefix


def test_the_pure_modules_do_not_load_sqlalchemy_or_the_repositories():
    result = run_import_probe(["app.v2.domain.financing", "app.v2.candidates.financing_evidence"], cwd=REPO_ROOT)
    loaded = set(result.loaded)
    assert not any(m == "sqlalchemy" or m.startswith(("sqlalchemy.", "app.v2.repositories", "app.v2.db")) for m in loaded)
