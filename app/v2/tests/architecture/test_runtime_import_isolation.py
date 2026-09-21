"""
Runtime check in a clean subprocess: importing V2 must not pull in AI
providers, app.v2.ai, or legacy modules -- transitively, which the static
scan cannot see. Also proves the probe itself can detect a leak.
"""

from app.v2.tests.architecture.boundary_scanner import (
    REPO_ROOT,
    ZONE_AI,
    ZONE_DETERMINISTIC,
    ZONE_WIRING,
    is_forbidden_loaded_for_ai,
    is_forbidden_loaded_for_deterministic,
    scan_tree,
)
from app.v2.tests.architecture.runtime_probe import run_import_probe


def _summarize(names, limit=12):
    """Readable failure output: a leaked SDK drags in hundreds of submodules."""
    shown = ", ".join(names[:limit])
    return f"{shown} (+{len(names) - limit} more)" if len(names) > limit else shown


def test_deterministic_v2_modules_import_cleanly_without_ai_or_legacy():
    zones = scan_tree(REPO_ROOT).modules_by_zone
    modules = zones.get(ZONE_DETERMINISTIC, []) + zones.get(ZONE_WIRING, [])
    assert "app.v2" in modules

    probe = run_import_probe(modules, cwd=REPO_ROOT)

    assert probe.failed == {}, f"deterministic modules failed to import: {probe.failed}"
    leaked = [name for name in probe.loaded if is_forbidden_loaded_for_deterministic(name)]
    assert leaked == [], f"deterministic import loaded forbidden modules: {_summarize(leaked)}"


def test_ai_package_imports_without_persistence_or_legacy():
    modules = scan_tree(REPO_ROOT).modules_by_zone[ZONE_AI]
    assert "app.v2.ai" in modules

    probe = run_import_probe(modules, cwd=REPO_ROOT)

    assert probe.failed == {}, f"app.v2.ai modules failed to import: {probe.failed}"
    leaked = [name for name in probe.loaded if is_forbidden_loaded_for_ai(name)]
    assert leaked == [], f"app.v2.ai import loaded forbidden modules: {_summarize(leaked)}"


def test_probe_detects_direct_and_transitive_leaks(tmp_path):
    (tmp_path / "leakpkg").mkdir()
    (tmp_path / "leakpkg" / "__init__.py").write_text("")
    (tmp_path / "leakpkg" / "direct.py").write_text("import colorsys\n")
    (tmp_path / "leakpkg" / "via.py").write_text("from leakpkg import direct\n")
    (tmp_path / "leakpkg" / "clean.py").write_text("import json\n")

    def loaded(module):
        probe = run_import_probe([module], cwd=tmp_path, pythonpath=tmp_path)
        assert probe.failed == {}
        return "colorsys" in probe.loaded

    assert loaded("leakpkg.direct") is True
    assert loaded("leakpkg.via") is True          # transitive
    assert loaded("leakpkg.clean") is False


def test_probe_reports_import_failures_instead_of_hiding_them(tmp_path):
    (tmp_path / "brokenpkg.py").write_text("import module_that_does_not_exist_zz\n")
    probe = run_import_probe(["brokenpkg"], cwd=tmp_path, pythonpath=tmp_path)
    assert "brokenpkg" in probe.failed
