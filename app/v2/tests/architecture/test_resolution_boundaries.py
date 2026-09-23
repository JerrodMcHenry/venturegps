"""
The resolution boundary, structurally:

  - only the approved private writer touches the canonical tables, and only promotion imports it
  - only two, narrow, reviewed modules may import promotion itself: rules.py (the deterministic-rule-authority
    front door) and, since Increment 18.2.1, human_review.py (the human-authority front door for operational
    callers such as a local CLI) -- never a general application/tooling module directly (see
    app.v2.resolution.promotion's own docstring and app.v2.resolution.human_review's for the full reasoning)
  - AI (app.v2.ai) can never import resolution, promotion, the writer or the company repository
  - the candidate layer (including the proposer) can never reach promotion
  - nothing in the resolution package takes a confidence/score or names a model provider
  - no provider SDK, network module, AI env name or worker framework is reachable from it
"""

import ast
import re
from pathlib import Path

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import REPO_ROOT, extract_imports, module_name_for, scan_source, scan_tree
from app.v2.tests.architecture.canonical_write_scan import canonical_writes
from app.v2.tests.architecture.runtime_probe import run_import_probe

V2 = REPO_ROOT / "app" / "v2"
WRITER = "app/v2/resolution/_writes.py"
PROMOTION = "app/v2/resolution/promotion.py"
RULES = "app/v2/resolution/rules.py"
AI = "app/v2/ai/adapter.py"


def modules(root: Path = V2):
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        yield rel, path.read_text()


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


# ---------------- only approved modules write the canonical tables

def test_the_real_tree_writes_the_canonical_tables_only_from_the_private_writer():
    offenders = {rel: found for rel, src in modules() if (found := canonical_writes(src, rel))}
    assert offenders == {}, offenders
    writer_source = (REPO_ROOT / WRITER).read_text()
    assert canonical_writes(writer_source, WRITER) == []                      # approved: not flagged...
    assert canonical_writes(writer_source, "app/v2/resolution/other.py")      # ...but the same code anywhere else is


@pytest.mark.parametrize("source", [
    "from app.v2.db.tables import company_table\nconn.execute(company_table.insert())",
    "from app.v2.db.tables import company_table as c\nconn.execute(c.insert().values())",
    "from app.v2.db.tables import resolution_decision_table as d\nconn.execute(d.update().values(x=1))",
    "from app.v2.db.tables import company_name_table\nconn.execute(company_name_table.delete())",
    "from sqlalchemy import insert\nfrom app.v2.db.tables import company_identifier_table as ci\nconn.execute(insert(ci))",
    "from sqlalchemy.dialects.postgresql import insert as pg_insert\nfrom app.v2.db.tables import company_table\npg_insert(company_table)",
    "from app.v2.db.tables import company_table\nalias = company_table\nalias.insert()",
    'conn.execute(text("INSERT INTO v2.company DEFAULT VALUES"))',
    'conn.execute(text("insert into v2.resolution_decision (a) values (1)"))',
    'conn.execute(text("UPDATE v2.company_name SET name = 1"))',
    'conn.execute(text("DELETE FROM v2.company_identifier"))',
    'conn.execute(text("TRUNCATE v2.company CASCADE"))',
    'metadata.tables["v2.company"]',
])
@pytest.mark.parametrize("path", ["app/v2/repositories/sneaky.py", "app/v2/ingestion/sneaky.py", "app/v2/resolution/rules.py",
                                  "app/v2/resolution/promotion.py", "app/v2/candidates/service.py", "app/v2/ai/adapter.py"])
def test_the_write_scan_flags_a_canonical_write_anywhere_but_the_private_writer(source, path):
    assert canonical_writes(source, path), (source, path)
    assert canonical_writes(source, WRITER) == []


@pytest.mark.parametrize("source", [
    "from app.v2.db.tables import company_table\nconn.execute(select(company_table))",
    "from app.v2.db.tables import company_name_table as n\nselect(n.c.name).where(n.c.id == 1)",
    'conn.execute(text("SELECT * FROM v2.company"))',
    'conn.execute(text("INSERT INTO v2.company_candidate (a) VALUES (1)"))',            # candidate tables are a different layer
    'msg = "update the company name"',
])
def test_reads_and_other_tables_are_not_flagged(source):
    assert canonical_writes(source, "app/v2/repositories/companies.py") == []


def test_the_read_repository_never_writes():
    source = (REPO_ROOT / "app/v2/repositories/companies.py").read_text()
    code = re.sub(r'""".*?"""', "", source, flags=re.S)
    assert not re.search(r"\.(insert|update|delete)\(|\binsert\(|\bupdate\(|\bdelete\(|pg_insert", code)
    assert "_writes" not in code and "promotion" not in code


def test_only_promotion_imports_the_private_writer_and_only_rules_and_human_review_import_promotion():
    """Increment 18.2.1: `promoters` was `{"app.v2.resolution.rules"}` until a real operational caller for the
    HUMAN side of promotion (a local, human-confirmed CLI) needed one and found none existed. The fix is not to
    add that caller here directly -- a CLI can grow new commands and new imports over time, and "any module
    under app.v2.tools may reach promotion" would be a materially broader grant than "exactly one small,
    reviewed module may". app.v2.resolution.human_review is that module: the human-authority counterpart to
    rules.py's rule-authority front door, adding no logic of its own (see its own docstring). This assertion
    stays a closed, explicit set of exactly two names -- not a package prefix, not a pattern -- so a THIRD
    caller still requires a deliberate, reviewed change here, not an incidental one."""
    importers, promoters = set(), set()
    for rel, src in modules():
        module, is_package = module_name_for(rel)
        for ref in extract_imports(ast.parse(src), module, is_package):
            target = ref.name or ""
            if target == "app.v2.resolution._writes" or target.startswith("app.v2.resolution._writes."):
                importers.add(module)
            if target == "app.v2.resolution.promotion" or target.startswith("app.v2.resolution.promotion."):
                promoters.add(module)
    assert importers <= set(DEFAULT_RULES.canonical_writer_importers) and importers == {"app.v2.resolution.promotion"}
    assert promoters == {"app.v2.resolution.rules", "app.v2.resolution.human_review"}


def test_a_create_company_function_exists_only_in_promotion_and_no_generic_repository_api_creates_companies():
    defs = {}
    for rel, src in modules():
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.search(r"(create|insert|add|save|upsert|write)_?(company|companies)", node.name):
                defs.setdefault(rel, []).append(node.name)
    assert defs == {WRITER: ["insert_company"], PROMOTION: ["create_company_from_candidate"]}


# ---------------- AI may propose, never decide or promote

@pytest.mark.parametrize("source", [
    "from app.v2.resolution import promotion", "from app.v2.resolution.promotion import create_company_from_candidate",
    "import app.v2.resolution.promotion", "from app.v2.resolution.rules import resolve_by_exact_identifier",
    "from app.v2.resolution._writes import insert_company", "from app.v2.resolution import _writes",
    "from app.v2.repositories.companies import get_company", "from app.v2.repositories import companies",
    "from app.v2.domain.resolution import human_authority",     # domain is allowed for AI... see the next test
])
def test_ai_cannot_import_the_promotion_boundary(source):
    found = rules_of(source, AI)
    if "app.v2.domain.resolution" in source:
        assert found == set()                    # the pure vocabulary (which has no AI member) is not a write path
    else:
        assert found & {"ai-imports-disallowed-v2-package", "ai-imports-persistence"}, source


@pytest.mark.parametrize("path", ["app/v2/candidates/proposer.py", "app/v2/candidates/evidence.py", "app/v2/candidates/service.py",
                                  "app/v2/repositories/company_candidates.py", "app/v2/candidates/new_finder.py"])
@pytest.mark.parametrize("source", ["from app.v2.resolution import promotion", "from app.v2.resolution.promotion import reject_candidate",
                                    "from app.v2.resolution.rules import resolve_by_exact_identifier", "import app.v2.resolution._writes",
                                    "from app.v2.repositories.companies import get_company"])
def test_the_candidate_layer_and_proposer_cannot_reach_promotion(source, path):
    assert "candidate-layer-imports-canonical" in rules_of(source, path)


def test_the_real_ai_zone_cannot_write_canonical_tables_even_if_it_existed(tmp_path):
    ai_dir = V2 / "ai"
    assert not ai_dir.exists() or all(canonical_writes(p.read_text(), p.relative_to(REPO_ROOT).as_posix()) == [] for p in ai_dir.rglob("*.py"))


# ---------------- nothing in the resolution package is probabilistic or provider-aware

def _identifiers(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name


def test_no_resolution_code_takes_or_names_confidence_scores_models_or_providers():
    forbidden = {"confidence", "score", "probability", "openai", "anthropic", "llm", "gpt", "prompt", "embedding",
                 "similarity", "fuzzy", "levenshtein"}
    for rel, src in modules():
        if not (rel.startswith("app/v2/resolution/") or rel in ("app/v2/repositories/companies.py", "app/v2/domain/resolution.py", "app/v2/domain/company.py")):
            continue
        names = {n for n in _identifiers(ast.parse(src))
                 if forbidden & set(re.sub(r"([a-z])([A-Z])", r"\1_\2", n).lower().split("_"))}
        assert not names, (rel, names)


def test_the_resolution_package_imports_no_provider_network_worker_or_legacy_code():
    for rel, src in modules():
        if rel.startswith("app/v2/resolution/") or rel in ("app/v2/repositories/companies.py",):
            assert scan_source(src, rel) == [], rel
            for banned in ("openai", "anthropic", "httpx", "requests", "socket", "celery", "app.ai", "app.api", "app.database", "app.v2.ai"):
                assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}\b", src, re.M), (rel, banned)


def test_the_scanner_bites_on_the_resolution_package():
    real = (REPO_ROOT / PROMOTION).read_text()
    assert scan_source(real, PROMOTION) == []
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import adapter\n", PROMOTION)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", PROMOTION)
    assert "network-import-forbidden" in rules_of(real + "\nimport httpx\n", PROMOTION)
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "OPENAI_API_KEY"\n', PROMOTION)
    assert "deterministic-imports-worker-framework" in rules_of(real + "\nimport celery\n", PROMOTION)


def test_the_whole_tree_is_clean_and_the_resolution_package_is_scanned():
    result = scan_tree()
    assert result.violations == []
    assert any(f.endswith("resolution/promotion.py") for f in result.files_scanned)


def test_runtime_import_of_the_boundary_loads_no_provider_network_or_legacy_modules():
    names = ["app.v2.resolution.promotion", "app.v2.resolution.rules", "app.v2.repositories.companies",
             "app.v2.domain.resolution", "app.v2.domain.company"]
    result = run_import_probe(names, cwd=REPO_ROOT)
    assert result.failed == {}
    loaded = set(result.loaded)
    for prefix in ("openai", "anthropic", "tavily", "langchain", "requests", "httpx", "aiohttp", "urllib3", "celery", "redis",
                   "app.v2.ai", "app.api", "app.ai", "app.database", "app.models", "app.workflows"):
        assert not any(m == prefix or m.startswith(prefix + ".") for m in loaded), prefix


def test_the_pure_domain_modules_stay_pure_and_the_domain_cannot_import_resolution_packages():
    for path in ("app/v2/domain/company.py", "app/v2/domain/resolution.py"):
        assert scan_source((REPO_ROOT / path).read_text(), path) == []
        assert rules_of("from app.v2.resolution import promotion", path)              # the pure layer cannot import upward
