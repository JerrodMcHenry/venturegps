"""
The scanner must PROVE it catches deliberately invalid code. If any of
these stop failing, the boundary tests elsewhere are meaningless.
"""

import pytest

from app.v2.tests.architecture.boundary_scanner import scan_source

DET = "app/v2/core/sample.py"   # deterministic zone, NOT pure (pure rules: test_pure_zone_rules.py)
AI = "app/v2/ai/sample.py"        # ai zone
WIRING = "app/v2/wiring.py"

PROVIDER = "deterministic-imports-provider-sdk"
IMPORTS_AI = "deterministic-imports-ai"
LEGACY = "deterministic-imports-legacy"
ENV = "deterministic-references-ai-env"
DYNAMIC = "dynamic-import-unresolvable"
AI_PERSIST = "ai-imports-persistence"
AI_V2 = "ai-imports-disallowed-v2-package"
AI_LEGACY = "ai-imports-legacy"


def rules_of(source: str, path: str) -> set[str]:
    return {v.rule for v in scan_source(source, path)}


# ------------------------------------------------- deterministic -> AI/provider

@pytest.mark.parametrize(
    "source",
    [
        "import openai",
        "from openai import OpenAI",
        "import openai.types as t",
        "import anthropic",
        "from anthropic import Anthropic",
        "import tavily",
        "from tavily import TavilyClient",
        "import langchain",
        "import langchain_openai",
        "from langchain_community.chat_models import ChatOpenAI",
        "import google.generativeai as genai",
        "from google import generativeai",
        "import cohere",
        "import litellm",
        "import tiktoken",
        "def f():\n    import openai\n    return openai",
        "try:\n    import anthropic\nexcept ImportError:\n    anthropic = None",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from openai import OpenAI",
        'import importlib\nimportlib.import_module("openai")',
        '__import__("anthropic")',
    ],
)
def test_deterministic_code_cannot_import_provider_sdks(source):
    assert PROVIDER in rules_of(source, DET)


@pytest.mark.parametrize(
    "source",
    [
        "import app.v2.ai",
        "import app.v2.ai.proposer",
        "from app.v2 import ai",
        "from app.v2.ai import proposer",
        "from app.v2.ai.proposer import Proposer",
        "from . import x\nfrom .. import ai",           # relative, from app/v2/core/sample.py
        "from ..ai import proposer",
        "from ..ai.proposer import Proposer",
        'import importlib\nimportlib.import_module("app.v2.ai.proposer")',
        "def f():\n    from app.v2.ai import proposer",
    ],
)
def test_deterministic_code_cannot_import_app_v2_ai(source):
    assert IMPORTS_AI in rules_of(source, DET)


def test_relative_import_of_ai_from_package_init_and_top_level():
    assert IMPORTS_AI in rules_of("from . import ai", "app/v2/__init__.py")
    assert IMPORTS_AI in rules_of("from .ai import x", "app/v2/somemodule.py")
    assert IMPORTS_AI in rules_of("from ... import ai", "app/v2/core/deep/sample.py")


@pytest.mark.parametrize(
    "source",
    [
        "from app.ai.scoring import finalize_pillar_score",
        "import app.database.db",
        "from app import api",
        "from app.models.startup import SIEMethodologyAnalysis",
        "from app.workflows.due_diligence_workflow import run_due_diligence",
        "from app.auth import RequireAdmin",
    ],
)
def test_deterministic_code_cannot_import_legacy_modules(source):
    assert LEGACY in rules_of(source, DET)


# ------------------------------------------------------- AI/search config names

@pytest.mark.parametrize(
    "source",
    [
        'import os\nos.getenv("OPENAI_API_KEY")',
        'import os\nos.environ["ANTHROPIC_API_KEY"]',
        'import os\nos.environ.get("TAVILY_API_KEY")',
        'import os\nos.getenv("openai_api_key")',
        'OPENAI_API_KEY = "sk-test"',
        "class Settings:\n    anthropic_api_key: str = ''",
        "def build(tavily_api_key):\n    return tavily_api_key",
        "build(openai_api_key=None)",
        "settings.openai_api_key",
        'import os\nurl = f"x-{os.environ[\'OPENAI_API_KEY\']}"',
        'KEYS = ["A", "some_TAVILY_API_KEY_value"]',
    ],
)
def test_deterministic_code_cannot_reference_ai_credentials(source):
    assert ENV in rules_of(source, DET)


# ----------------------------------------------------- dynamic / unparseable

@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module(name)",
        "__import__(name)",
        'import importlib\nimportlib.import_module(".sibling", __package__)',
        'import importlib\nimportlib.import_module("a" + "b")',
    ],
)
def test_unresolvable_dynamic_imports_fail_closed(source):
    assert DYNAMIC in rules_of(source, DET)
    assert DYNAMIC in rules_of(source, AI)


def test_unparseable_source_fails_closed():
    assert "unparseable-source" in rules_of("def broken(:\n", DET)


# ---------------------------------------------------------------- ai zone

@pytest.mark.parametrize(
    "source",
    [
        "from app.v2.repositories.companies import CompanyRepository",
        "import app.v2.repositories",
        "from app.v2 import repositories",
        "from .. import repositories",                     # relative from app/v2/ai/sample.py
        "from ..repositories import sources",
        "from app.v2.db.engine import get_engine",
        "from app.v2.db import tables",
        "from app.v2.workers.runner import run_once",
        "import sqlalchemy",
        "from sqlalchemy import text",
        "from sqlalchemy.orm import Session",
        "import psycopg2",
        "import psycopg",
        "import asyncpg",
        "import alembic",
        "def f():\n    from app.v2.repositories import x",
        'import importlib\nimportlib.import_module("app.v2.repositories.sources")',
    ],
)
def test_ai_package_cannot_import_repositories_db_or_sql_drivers(source):
    assert AI_PERSIST in rules_of(source, AI)


@pytest.mark.parametrize(
    "source",
    [
        "from app.v2.signals import engine",
        "from app.v2.resolution import promotion",         # the whole resolution boundary is closed to AI
        "from app.v2.resolution.promotion import create_company_from_candidate",
        "from app.v2.resolution.rules import resolve_by_exact_identifier",
        "from app.v2.resolution._writes import insert_company",
        "import app.v2.resolution",
        "from app.v2 import resolution",

        "import app.v2.observations.ingest",
    ],
)
def test_ai_package_default_denies_other_v2_packages(source):
    assert AI_V2 in rules_of(source, AI)


@pytest.mark.parametrize(
    "source",
    [
        "from app.ai.scoring import finalize_pillar_score",
        "import app.database.db",
        "from app import database",
    ],
)
def test_ai_package_cannot_import_legacy_modules(source):
    assert AI_LEGACY in rules_of(source, AI)


# -------------------------------------------------------------- wiring zone

def test_wiring_module_may_import_ai_but_nothing_else_forbidden():
    assert rules_of("from app.v2.ai import proposer", WIRING) == set()
    assert PROVIDER in rules_of("import openai", WIRING)
    assert ENV in rules_of('import os\nos.getenv("OPENAI_API_KEY")', WIRING)
    assert LEGACY in rules_of("import app.database.db", WIRING)
