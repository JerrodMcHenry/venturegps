"""
The Candidate layer: the proposer boundary, no canonical writes, no AI/network, pure modules stay pure.

Probabilistic proposal -> deterministic validation -> untrusted stored candidate -> (future) resolution.
"""

import re

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import (
    REPO_ROOT,
    is_forbidden_loaded_for_network,
    is_forbidden_loaded_for_pure,
    scan_source,
    scan_tree,
)
from app.v2.tests.architecture.runtime_probe import run_import_probe

PROPOSER = "app/v2/candidates/proposer.py"
EVIDENCE = "app/v2/candidates/evidence.py"
SERVICE = "app/v2/candidates/service.py"
REPO_FILE = "app/v2/repositories/company_candidates.py"
DOMAIN = "app/v2/domain/candidate.py"
PURE_FILES = (PROPOSER, EVIDENCE, DOMAIN)
FUTURE_CANONICAL = ["from app.v2.resolution import decisions", "import app.v2.resolution.rules", "from app.v2 import resolution",
                    "from app.v2.promotion import promote_candidate", "import app.v2.canonical", "from app.v2.companies import create_company",
                    "from app.v2.claims import add_claim", "import app.v2.evidence_links", "from app.v2 import resolution_decisions"]


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


def test_the_candidate_modules_exist_are_scanned_and_clean():
    result = scan_tree(REPO_ROOT)
    assert {PROPOSER, EVIDENCE, SERVICE, REPO_FILE, DOMAIN, "app/v2/candidates/__init__.py",
            "app/v2/migrations/versions/0006_create_company_candidate.py"} <= set(result.files_scanned)
    assert not [v for v in result.violations if v.path.startswith("app/v2/candidates/") or v.path in (REPO_FILE, DOMAIN)]


# ---------------- the proposer port and evidence verifier are pure

@pytest.mark.parametrize("path", [PROPOSER, EVIDENCE])
@pytest.mark.parametrize("source", [
    "from app.v2.repositories import company_candidates", "from app.v2.repositories.company_candidates import store_company_candidates",
    "from app.v2.db.tables import company_candidate_table", "from app.v2.db import engine", "import sqlalchemy", "from sqlalchemy import text",
    "from app.v2.candidates.service import persist_verified_candidates", "from app.v2.ingestion.service import ingest_evidence",
    "import os", "import socket", "import subprocess", "from app.v2.config import get_database_url",
])
def test_the_proposer_port_and_evidence_verifier_cannot_reach_repositories_the_database_or_the_environment(source, path):
    assert rules_of(source, path) & {"pure-imports-forbidden", "pure-imports-disallowed-v2-package"}, source


@pytest.mark.parametrize("path", [PROPOSER, EVIDENCE])
def test_the_real_pure_modules_pass_and_stay_pure(path):
    real = (REPO_ROOT / path).read_text()
    assert scan_source(real, path) == []
    for bad in ("import openai", "from anthropic import Anthropic", "import httpx", "import requests"):
        assert rules_of(bad, path), bad
    assert "deterministic-imports-ai" in rules_of("from app.v2 import ai", path)
    assert "deterministic-references-ai-env" in rules_of('k = "OPENAI_API_KEY"', path)


def test_the_pure_layers_stay_ordered_the_domain_never_imports_candidates():
    for source in ("from app.v2.candidates.evidence import verify_proposal", "from app.v2.candidates import proposer"):
        assert "layer-violation" in rules_of(source, DOMAIN)
        assert "layer-violation" in rules_of(source, "app/v2/observations/hashing.py")
    assert rules_of("from app.v2.domain.candidate import CompanyCandidateProposal", EVIDENCE) == set()
    assert rules_of("from app.v2.observations.hashing import compute_content_hash", EVIDENCE) == set()


# ---------------- the candidate layer can never promote canonical truth

@pytest.mark.parametrize("path", [PROPOSER, EVIDENCE, SERVICE, REPO_FILE, "app/v2/candidates/anything_new.py"])
@pytest.mark.parametrize("source", FUTURE_CANONICAL)
def test_the_candidate_layer_cannot_import_any_resolution_promotion_or_canonical_package(source, path):
    assert "candidate-layer-imports-canonical" in rules_of(source, path), (source, path)


def test_the_canonical_rule_is_structural_no_such_packages_were_created():
    for name in ("promotion", "canonical", "companies", "claims", "evidence_links", "resolution_decisions", "workers"):
        assert not (REPO_ROOT / "app/v2" / name).exists(), name
    assert set(DEFAULT_RULES.canonical_forbidden_import_prefixes) >= {"app.v2.resolution", "app.v2.promotion", "app.v2.canonical"}


def test_the_candidate_repository_writes_only_candidate_tables():
    source = (REPO_ROOT / REPO_FILE).read_text()
    inserted = set(re.findall(r"(?:pg_)?insert\((\w+)\)", source))
    assert inserted == {"cc", "ci"}                                            # company_candidate and its identifiers only
    imported_tables = set(re.findall(r"import (\w+_table) as \w+", source))
    assert imported_tables == {"company_candidate_identifier_table", "company_candidate_table", "observation_table", "processing_attempt_table"}
    from app.v2.db import tables  # noqa: F401 - registers every V2 table on the metadata
    from app.v2.db.metadata import metadata
    assert sorted(metadata.tables) == ["v2.company", "v2.company_candidate", "v2.company_candidate_identifier",
                                       "v2.company_identifier", "v2.company_market_classification", "v2.company_name",
                                       "v2.financing_event", "v2.financing_event_candidate", "v2.financing_event_candidate_amount",
                                       "v2.financing_event_candidate_date", "v2.financing_event_date", "v2.financing_event_stage",
                                       "v2.financing_event_type", "v2.financing_event_verified_round_amount",
                                       "v2.financing_resolution_decision", "v2.market",
                                       "v2.observation", "v2.observation_sighting", "v2.processing_attempt", "v2.raw_payload",
                                       "v2.resolution_decision", "v2.source", "v2.taxonomy_version"]


def test_the_service_never_completes_or_promotes_anything():
    source = (REPO_ROOT / SERVICE).read_text()
    code = re.sub(r'""".*?"""', "", source, flags=re.S)
    for word in ("mark_processed", "mark_failed", "mark_quarantined", "promote", "canonical", "resolve"):
        assert word not in code, word


# ---------------- no AI, no network anywhere in the candidate layer

@pytest.mark.parametrize("path", [SERVICE, REPO_FILE])
def test_the_rules_bite_on_the_service_and_repository_paths(path):
    real = (REPO_ROOT / path).read_text()
    assert scan_source(real, path) == []
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import proposer\n", path)
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", path)
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "ANTHROPIC_API_KEY"\n', path)
    assert "network-import-forbidden" in rules_of(real + "\nimport httpx\n", path)
    assert "deterministic-imports-worker-framework" in rules_of(real + "\nimport celery\n", path)


def test_ai_may_implement_the_port_but_cannot_reach_persistence_or_the_service():
    assert rules_of("from app.v2.candidates.proposer import CandidateProposer", "app/v2/ai/adapter.py") == set()
    assert rules_of("from app.v2.domain.candidate import CompanyCandidateProposal", "app/v2/ai/adapter.py") == set()
    for source in ("from app.v2.candidates.service import persist_verified_candidates", "from app.v2.candidates import service",
                   "from app.v2.candidates.evidence import verify_proposal", "from app.v2.repositories.company_candidates import store_company_candidates",
                   "from app.v2.db.tables import company_candidate_table"):
        assert rules_of(source, "app/v2/ai/adapter.py") & {"ai-imports-persistence", "ai-imports-disallowed-v2-package"}, source
    # the package root is only a docstring and an ancestor of the allowed port; its submodules stay default-denied
    assert rules_of("from app.v2 import candidates", "app/v2/ai/adapter.py") == set()


def test_no_ai_sdk_or_provider_is_installed_or_referenced():
    requirements = (REPO_ROOT / "requirements.txt").read_text().lower()
    assert "openai" in requirements                                            # legacy dependency, untouched...
    for path in (REPO_ROOT / "app/v2").rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith(("app/v2/tests/",)):
            continue
        text_ = path.read_text().lower()
        assert not re.search(r"^\s*(import|from)\s+(openai|anthropic|tavily)", text_, flags=re.M), rel


def test_importing_the_candidate_layer_loads_no_ai_network_or_legacy_module():
    pure = run_import_probe(["app.v2.candidates.proposer", "app.v2.candidates.evidence", "app.v2.domain.candidate"], cwd=REPO_ROOT)
    assert pure.failed == {} and [m for m in pure.loaded if is_forbidden_loaded_for_pure(m)] == []
    everything = run_import_probe(["app.v2.candidates", "app.v2.candidates.service", "app.v2.repositories.company_candidates"], cwd=REPO_ROOT)
    assert everything.failed == {} and [m for m in everything.loaded if is_forbidden_loaded_for_network(m)] == []
