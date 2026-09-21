"""The actual boundary check against the real app/v2 tree."""

from app.v2.tests.architecture.boundary_scanner import REPO_ROOT, ZONE_AI, ZONE_DETERMINISTIC, scan_tree


def test_real_v2_tree_respects_the_ai_boundary():
    result = scan_tree(REPO_ROOT)

    # Non-vacuous: the scanner really saw the package, in the right zones.
    assert "app/v2/__init__.py" in result.files_scanned
    assert "app/v2/ai/__init__.py" in result.files_scanned
    assert "app.v2" in result.modules_by_zone[ZONE_DETERMINISTIC]
    assert "app.v2.ai" in result.modules_by_zone[ZONE_AI]
    assert not any(path.startswith("app/v2/tests/") for path in result.files_scanned)

    assert not result.violations, "AI boundary violations:\n" + "\n".join(str(v) for v in result.violations)
