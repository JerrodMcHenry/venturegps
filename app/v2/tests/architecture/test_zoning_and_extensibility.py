"""Zoning is default-deny and rules are data, so new packages/deps are cheap to cover."""

from dataclasses import replace

import pytest

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES, matches_prefix
from app.v2.tests.architecture.boundary_scanner import (
    ZONE_AI,
    ZONE_DETERMINISTIC,
    ZONE_WIRING,
    scan_source,
    scan_tree,
    zone_for_path,
)


@pytest.mark.parametrize(
    "path, zone",
    [
        ("app/v2/__init__.py", ZONE_DETERMINISTIC),
        ("app/v2/domain/source.py", ZONE_DETERMINISTIC),
        ("app/v2/some_future_package/x.py", ZONE_DETERMINISTIC),   # default-deny: no registration needed
        ("app/v2/ai/__init__.py", ZONE_AI),
        ("app/v2/ai/adapters/openai_proposer.py", ZONE_AI),
        ("app/v2/ai.py", ZONE_AI),
        ("app/v2/aim/x.py", ZONE_DETERMINISTIC),                   # prefix boundary
        ("app/v2/aiops/x.py", ZONE_DETERMINISTIC),
        ("app/v2/wiring.py", ZONE_WIRING),
        ("app/v2/wiring/x.py", ZONE_DETERMINISTIC),
        ("app/v2/tests/architecture/x.py", None),
        ("app/v2/tests/conftest.py", None),
        ("app/v2/testsuite/x.py", ZONE_DETERMINISTIC),             # prefix boundary
        ("app/ai/scoring.py", None),
        ("app/database/db.py", None),
        ("app/v2/notes.md", None),
    ],
)
def test_zone_for_path(path, zone):
    assert zone_for_path(path) == zone


def test_matches_prefix_respects_dotted_boundaries():
    assert matches_prefix("a.b", ["a.b"])
    assert matches_prefix("a.b.c", ["a.b"])
    assert not matches_prefix("a.bc", ["a.b"])


def test_rules_are_extensible_without_touching_the_scanner():
    stricter = replace(
        DEFAULT_RULES,
        provider_sdk_prefixes=DEFAULT_RULES.provider_sdk_prefixes + ("brandnewllm",),
        forbidden_env_names=DEFAULT_RULES.forbidden_env_names + ("BRANDNEW_API_KEY",),
        ai_forbidden_import_prefixes=DEFAULT_RULES.ai_forbidden_import_prefixes + ("app.v2.exports",),
    )
    det = "app/v2/core/x.py"
    assert scan_source("import brandnewllm", det) == []
    assert scan_source("import brandnewllm", det, stricter) != []
    assert scan_source('k = "BRANDNEW_API_KEY"', det) == []
    assert scan_source('k = "BRANDNEW_API_KEY"', det, stricter) != []
    assert {v.rule for v in scan_source("import app.v2.exports", "app/v2/ai/x.py", stricter)} == {"ai-imports-persistence"}


def test_legacy_allowlist_is_closed_and_opt_in():
    # Increment 14: app.observability is the one explicit, documented exception (a logging/error-reporting sink,
    # never a source of canonical data or authority) -- everything else legacy stays forbidden by default.
    assert DEFAULT_RULES.legacy_import_allowlist == ("app.observability",)
    src = "from app.observability import capture_exception"
    assert scan_source(src, "app/v2/core/x.py") == []
    assert scan_source("import app.database.db", "app/v2/core/x.py") != []
    empty = replace(DEFAULT_RULES, legacy_import_allowlist=())
    assert scan_source(src, "app/v2/core/x.py", empty) != []


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scan_tree_finds_planted_violations_and_respects_zones(tmp_path):
    _write(tmp_path, "app/v2/__init__.py", "")
    _write(tmp_path, "app/v2/core/__init__.py", "")
    _write(tmp_path, "app/v2/core/bad_provider.py", "import openai\n")
    _write(tmp_path, "app/v2/core/bad_ai.py", "from app.v2 import ai\n")
    _write(tmp_path, "app/v2/core/bad_env.py", 'import os\nos.getenv("OPENAI_API_KEY")\n')
    _write(tmp_path, "app/v2/signals/x.py", "import anthropic\n")            # never-registered package
    _write(tmp_path, "app/v2/ai/__init__.py", "")
    _write(tmp_path, "app/v2/ai/ok_provider.py", "import openai\n")           # allowed in ai
    _write(tmp_path, "app/v2/ai/bad_persistence.py", "from app.v2.repositories import x\n")
    _write(tmp_path, "app/v2/tests/test_excluded.py", "import openai\nfrom app.v2 import ai\n")
    _write(tmp_path, "app/v2/core/broken.py", "def broken(:\n")

    result = scan_tree(tmp_path)
    by_file = {}
    for v in result.violations:
        by_file.setdefault(v.path, set()).add(v.rule)

    assert by_file == {
        "app/v2/core/bad_provider.py": {"deterministic-imports-provider-sdk"},
        "app/v2/core/bad_ai.py": {"deterministic-imports-ai"},
        "app/v2/core/bad_env.py": {"deterministic-references-ai-env"},
        "app/v2/signals/x.py": {"deterministic-imports-provider-sdk"},
        "app/v2/ai/bad_persistence.py": {"ai-imports-persistence"},
        "app/v2/core/broken.py": {"unparseable-source"},
    }
    assert "app/v2/tests/test_excluded.py" not in result.files_scanned
    assert "app/v2/ai/ok_provider.py" in result.files_scanned
    assert "app.v2.ai.ok_provider" in result.modules_by_zone[ZONE_AI]
    assert "app.v2.signals.x" in result.modules_by_zone[ZONE_DETERMINISTIC]


def test_scan_tree_on_missing_v2_dir_is_empty(tmp_path):
    assert scan_tree(tmp_path).files_scanned == []
