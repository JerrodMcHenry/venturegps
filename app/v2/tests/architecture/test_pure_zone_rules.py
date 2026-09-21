"""
The stricter rules for pure packages (app.v2.domain, app.v2.observations):
no database/SQL, persistence/worker/config/migration packages, network,
processes or environment access, and one-way layering.
"""

from dataclasses import replace

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES
from app.v2.tests.architecture.boundary_scanner import ZONE_DETERMINISTIC, REPO_ROOT, scan_source, scan_tree

DOMAIN = "app/v2/domain/sample.py"
OBSERVATIONS = "app/v2/observations/sample.py"
NESTED = "app/v2/domain/sub/sample.py"
NOT_PURE = "app/v2/core/sample.py"


def rules_of(source, path):
    return {v.rule for v in scan_source(source, path)}


@pytest.mark.parametrize("path", [DOMAIN, OBSERVATIONS, NESTED])
@pytest.mark.parametrize(
    "source",
    [
        # database / SQL
        "import sqlalchemy", "from sqlalchemy import text", "import alembic", "import psycopg2",
        "import psycopg", "import asyncpg", "import sqlite3",
        # V2 persistence, workers, configuration, migrations
        "from app.v2.db import engine", "from app.v2.db.engine import make_engine", "import app.v2.db",
        "from app.v2 import db", "from app.v2.config import get_database_url", "from app.v2 import config",
        "from app.v2.repositories import sources", "from app.v2.workers import runner",
        "from app.v2.migrations import env",
        # environment, processes, network
        "import os", "import os.path", "from os import path", "import subprocess", "import socket", "import ssl",
        "import http.client", "import urllib.request", "from urllib import request", "import urllib3",
        "import requests", "import httpx", "import aiohttp", "import websockets", "import dotenv",
        "def f():\n    import os", "try:\n    import requests\nexcept ImportError:\n    pass",
        'import importlib\nimportlib.import_module("sqlalchemy")',
        '__import__("os")',
    ],
)
def test_pure_modules_cannot_import_io_modules(source, path):
    assert "pure-imports-forbidden" in rules_of(source, path)


@pytest.mark.parametrize("path", [DOMAIN, OBSERVATIONS])
@pytest.mark.parametrize(
    "source",
    ["x = environ", "getenv('A')", "thing.environ", "thing.getenv('A')", "from os import getenv", "from os import environ as e"],
)
def test_pure_modules_cannot_mention_environment_access(source, path):
    assert "pure-reads-environment" in rules_of(source, path)


@pytest.mark.parametrize("path", [DOMAIN, OBSERVATIONS])
@pytest.mark.parametrize(
    "source",
    ["from app.v2.some_future_package import x", "import app.v2.signals", "from app.v2 import signals"],
)
def test_pure_modules_cannot_import_other_v2_packages(source, path):
    assert "pure-imports-disallowed-v2-package" in rules_of(source, path)


def test_pure_modules_still_cannot_import_ai_or_legacy():
    assert "deterministic-imports-ai" in rules_of("from app.v2 import ai", DOMAIN)
    assert "deterministic-imports-provider-sdk" in rules_of("import openai", OBSERVATIONS)
    assert "deterministic-imports-legacy" in rules_of("from app.database.db import engine", DOMAIN)
    assert "deterministic-references-ai-env" in rules_of('k = "OPENAI_API_KEY"', OBSERVATIONS)


def test_domain_may_not_import_the_observations_layer_but_observations_may_import_domain():
    assert "layer-violation" in rules_of("from app.v2.observations import hashing", DOMAIN)
    assert "layer-violation" in rules_of("import app.v2.observations.media", NESTED)
    assert "layer-violation" in rules_of("from ... import observations", NESTED)  # app.v2.domain.sub -> app.v2
    assert "layer-violation" in rules_of("from .. import observations", "app/v2/domain/sample.py")
    assert rules_of("from app.v2.domain.errors import InvalidInputError\nfrom app.v2.domain import content", OBSERVATIONS) == set()


@pytest.mark.parametrize("path", [DOMAIN, OBSERVATIONS])
@pytest.mark.parametrize(
    "source",
    [
        "import hashlib, json, re, enum, datetime, typing",
        "from datetime import datetime, timezone\nfrom enum import Enum",
        "from urllib.parse import urlsplit",
        "from urllib import parse",
        "import pydantic\nfrom pydantic import BaseModel, AfterValidator",
        "import app.v2\nfrom app.v2.domain.errors import InvalidInputError",
        "from app.v2.domain import time as t",
        "from . import errors",
        "from .errors import InvalidInputError",
        '"""Docstring mentioning environ, os and sqlalchemy is fine."""\nx = 1',
    ],
)
def test_legitimate_pure_code_passes(source, path):
    assert rules_of(source, path) == set()


def test_pure_rules_do_not_apply_outside_the_pure_packages():
    assert rules_of("import os\nimport sqlalchemy\nfrom app.v2.config import get_database_url\nx = environ", NOT_PURE) == set()
    assert rules_of("import sqlalchemy\nfrom app.v2.db.engine import get_engine", "app/v2/db/sample.py") == set()


def test_pure_packages_and_layers_are_configurable():
    stricter = replace(DEFAULT_RULES, pure_packages=DEFAULT_RULES.pure_packages + ("app.v2.core",))
    assert scan_source("import os", NOT_PURE) == []
    assert scan_source("import os", NOT_PURE, stricter) != []


def test_real_pure_modules_exist_and_are_scanned():
    result = scan_tree(REPO_ROOT)
    scanned = set(result.modules_by_zone[ZONE_DETERMINISTIC])
    assert {"app.v2.domain.time", "app.v2.domain.versions", "app.v2.domain.errors", "app.v2.domain.source",
            "app.v2.domain.observation", "app.v2.domain.processing", "app.v2.domain.content",
            "app.v2.observations.hashing", "app.v2.observations.media"} <= scanned
    assert not result.violations
