"""Ingestion stays deterministic: no network, no AI, no legacy, and persistence stays out of the pure domain."""

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import (
    REPO_ROOT,
    is_forbidden_loaded_for_network,
    scan_source,
    scan_tree,
)
from app.v2.tests.architecture.runtime_probe import run_import_probe

INGESTION_FILES = ("app/v2/ingestion/service.py", "app/v2/ingestion/models.py", "app/v2/ingestion/errors.py")
NETWORK_IMPORTS = [
    "import socket", "import ssl", "import http.client", "from http import client", "import urllib.request",
    "from urllib import request", "import urllib3", "import requests", "import httpx", "import aiohttp",
    "import websockets", "import ftplib", "import smtplib", "import dns.resolver", "from dns import resolver",
    'import importlib\nimportlib.import_module("httpx")', '__import__("socket")',
]


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


def test_the_ingestion_modules_exist_are_scanned_and_clean():
    result = scan_tree(REPO_ROOT)
    assert set(INGESTION_FILES) | {"app/v2/ingestion/__init__.py", "app/v2/repositories/sightings.py", "app/v2/domain/sighting.py"} <= set(result.files_scanned)
    assert not [v for v in result.violations if v.path.startswith(("app/v2/ingestion/", "app/v2/repositories/")) or v.path.endswith("sighting.py")]


@pytest.mark.parametrize("path", [*INGESTION_FILES, "app/v2/repositories/sightings.py", "app/v2/repositories/observations.py", "app/v2/ingestion/new_module.py"])
@pytest.mark.parametrize("source", NETWORK_IMPORTS)
def test_ingestion_and_repositories_cannot_import_network_modules(source, path):
    assert "network-import-forbidden" in rules_of(source, path)


def test_the_network_rule_is_limited_to_the_configured_packages_and_is_configurable():
    assert rules_of("import socket", "app/v2/core/x.py") == set()                      # other deterministic code is not covered
    assert rules_of("from urllib.parse import urlsplit", "app/v2/ingestion/x.py") == set()  # parsing is not networking
    assert DEFAULT_RULES.no_network_packages == (
        "app.v2.ingestion", "app.v2.repositories", "app.v2.candidates", "app.v2.resolution", "app.v2.financing_resolution",
    )


def test_the_real_service_source_is_clean_and_the_rules_bite_on_its_path():
    real = (REPO_ROOT / "app/v2/ingestion/service.py").read_text()
    assert scan_source(real, "app/v2/ingestion/service.py") == []
    assert "deterministic-imports-ai" in rules_of(real + "\nfrom app.v2.ai import proposer\n", "app/v2/ingestion/service.py")
    assert "deterministic-imports-provider-sdk" in rules_of(real + "\nimport openai\n", "app/v2/ingestion/service.py")
    assert "deterministic-references-ai-env" in rules_of(real + '\nk = "OPENAI_API_KEY"\n', "app/v2/ingestion/service.py")
    assert "deterministic-imports-legacy" in rules_of(real + "\nfrom app.website_scrapper import extract_text_from_website\n", "app/v2/ingestion/service.py")
    assert "network-import-forbidden" in rules_of(real + "\nimport httpx\n", "app/v2/ingestion/service.py")


def test_ai_and_the_pure_domain_cannot_reach_ingestion_or_sightings():
    for source in ("from app.v2.ingestion.service import ingest_evidence", "from app.v2 import ingestion",
                   "from app.v2.repositories.sightings import store_sighting"):
        assert rules_of(source, "app/v2/ai/adapter.py") & {"ai-imports-persistence", "ai-imports-disallowed-v2-package"}, source
        assert "pure-imports-forbidden" in rules_of(source, "app/v2/domain/sighting.py") or "pure-imports-disallowed-v2-package" in rules_of(source, "app/v2/domain/sighting.py"), source


def test_the_new_domain_module_is_pure():
    real = (REPO_ROOT / "app/v2/domain/sighting.py").read_text()
    assert scan_source(real, "app/v2/domain/sighting.py") == []
    for bad in ("import sqlalchemy", "import os", "import socket", "from app.v2.repositories import sightings"):
        assert "pure-imports-forbidden" in rules_of(bad, "app/v2/domain/sighting.py"), bad


def test_importing_ingestion_loads_no_network_client_ai_provider_or_legacy_module():
    probe = run_import_probe(["app.v2.ingestion", "app.v2.ingestion.service", "app.v2.ingestion.models",
                              "app.v2.repositories.sightings"], cwd=REPO_ROOT)
    assert probe.failed == {}
    assert [m for m in probe.loaded if is_forbidden_loaded_for_network(m)] == []
