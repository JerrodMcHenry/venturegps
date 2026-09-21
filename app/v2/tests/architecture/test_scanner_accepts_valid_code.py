"""The scanner must not cry wolf: legitimate code passes."""

import pytest

from app.v2.tests.architecture.boundary_scanner import scan_source


def violations(source: str, path: str):
    return [str(v) for v in scan_source(source, path)]


@pytest.mark.parametrize(
    "source",
    [
        "import hashlib, json, re\nfrom dataclasses import dataclass",
        "import pydantic\nfrom pydantic import BaseModel",
        "import sqlalchemy\nfrom sqlalchemy import text",              # persistence is fine outside ai
        "import alembic",
        "import app.v2\nfrom app.v2.domain import observation",
        "from . import sibling\nfrom .sibling import thing",           # relative, stays inside V2
        "from app.v2.aimodule import x",                               # 'ai' prefix boundary: not app.v2.ai
        "from app.v2.aim import x",
        "import openaiish_but_not_openai_lookalike",                   # different top-level name
        "import importlib\nimportlib.import_module('json')",
        '"""Module docstring may mention OPENAI_API_KEY and openai."""\nx = 1',
        'def f():\n    """Docstring naming ANTHROPIC_API_KEY."""\n    return 1',
        "# OPENAI_API_KEY only in a comment\nx = 1",
        "class Repo:\n    '''TAVILY_API_KEY documented here.'''\n",
    ],
)
def test_valid_deterministic_code_passes(source):
    assert violations(source, "app/v2/core/sample.py") == []


@pytest.mark.parametrize(
    "source",
    [
        "import openai",
        "from anthropic import Anthropic",
        "import tiktoken",
        'import os\nkey = os.environ["OPENAI_API_KEY"]',                # ai zone owns its provider config
        "from app.v2.domain.candidate import CompanyCandidate",
        "import app.v2",
        "from app.v2 import domain",
        "from . import sibling\nfrom .. import domain",                # relative, within ai's allowance
        "import pydantic, httpx",
    ],
)
def test_valid_ai_code_passes(source):
    assert violations(source, "app/v2/ai/sample.py") == []


def test_wiring_module_is_the_only_deterministic_module_allowed_to_import_ai():
    assert violations("from app.v2.ai import proposer\nimport app.v2.ai", "app/v2/wiring.py") == []
    assert violations("from app.v2.ai import proposer", "app/v2/wiring_helper.py") != []


def test_files_outside_v2_and_test_files_are_not_scanned():
    bad = "import openai\nfrom app.v2 import ai"
    assert violations(bad, "app/v2/tests/architecture/sample.py") == []
    assert violations(bad, "app/v2/tests/test_something.py") == []
    assert violations(bad, "app/ai/legacy_module.py") == []
    assert violations(bad, "dashboard/whatever.py") == []
    assert violations(bad, "app/v2/README.md") == []
