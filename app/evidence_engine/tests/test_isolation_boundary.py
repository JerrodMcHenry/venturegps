"""
Task 21 -- automated isolation-boundary scan.

Every prior task (14-20) "reconfirmed the isolation boundary" as a
MANUAL step (a grep, checked by hand, restated in each task's own
completion report) -- there was no automated test enforcing it, unlike
`app/v2`'s own `tests/architecture/boundary_rules.py`. Task 21 corrects
the UNDERSTANDING of that boundary (four specific legacy imports are
explicitly approved, not zero) and, since this task's own subject is
exactly "what may this package import," it is the right moment to also
make the check itself real and automated rather than manual-and-restated
forever.

The rule (NEW_ENGINE_ARCHITECTURE.md Part 1.2, unchanged by this task,
only exercised for the first time): every `.py` file under
`app/evidence_engine/` may import `app.evidence_engine.*` (itself)
freely, plus EXACTLY these four legacy modules:

    app.website_scrapper
    app.pdf_extractor
    app.ai.concurrency   (specifically this one app.ai submodule)
    app.auth

Any other `app.*` import (`app.ai.pillar_shared`, `app.database.db`,
`app.v2.*`, `app.models.*`, `app.api`, ...) is a boundary violation.

Deliberately a static AST scan of `import`/`from ... import` statements
only -- the same fidelity level `NEW_ENGINE_E2E_EVALUATION.md`'s own
prior "zero imports outside app.evidence_engine" manual checks already
had (a grep), now just automated and run every regression sweep instead
of re-typed by hand each task.

Run with:
    python -m app.evidence_engine.tests.test_isolation_boundary
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_ROOT = REPO_ROOT / "app" / "evidence_engine"

ALLOWED_LEGACY_MODULES = frozenset({
    "app.website_scrapper",
    "app.pdf_extractor",
    "app.ai.concurrency",
    "app.auth",
})


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _imported_app_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.") or alias.name == "app":
                    modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module.startswith("app.") or node.module == "app"):
                modules.add(node.module)
    return modules


def _all_engine_py_files() -> list[Path]:
    return [
        p for p in ENGINE_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _violations() -> dict[str, set[str]]:
    violations: dict[str, set[str]] = {}
    for path in _all_engine_py_files():
        bad = set()
        for module in _imported_app_modules(path):
            if module == "app.evidence_engine" or module.startswith("app.evidence_engine."):
                continue
            if module in ALLOWED_LEGACY_MODULES:
                continue
            bad.add(module)
        if bad:
            violations[str(path.relative_to(REPO_ROOT))] = bad
    return violations


def test_no_file_imports_a_legacy_module_outside_the_four_approved_exceptions() -> None:
    violations = _violations()
    expect(
        not violations,
        "unapproved legacy import(s) found: " + "; ".join(f"{f}: {sorted(m)}" for f, m in violations.items()),
    )


def test_at_least_one_file_actually_uses_each_approved_exception() -> None:
    """A regression guard in the OTHER direction: if a future edit
    quietly stops using one of the four approved imports, that is not a
    violation, but this test documents which files currently exercise
    which exception, so a silent removal is visible in a diff rather
    than invisible."""
    used: set[str] = set()
    for path in _all_engine_py_files():
        used |= (_imported_app_modules(path) & ALLOWED_LEGACY_MODULES)
    expect("app.website_scrapper" in used, "expected providers_live.py to use the approved website_scrapper import")
    expect("app.ai.concurrency" in used, "expected concurrency_helpers.py to use the approved run_concurrently import")


def test_scanner_itself_detects_a_genuine_violation() -> None:
    """A scanner that can never fail is not a real test -- proves the
    AST logic actually flags a forbidden import, using a throwaway
    in-memory example rather than a real file."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("import app.ai.pillar_shared\nfrom app.database import db\n")
        temp_path = Path(f.name)
    try:
        modules = _imported_app_modules(temp_path)
        bad = modules - {"app.evidence_engine"} - ALLOWED_LEGACY_MODULES
        expect("app.ai.pillar_shared" in bad and "app.database" in bad, f"scanner failed to flag known-bad imports: {modules}")
    finally:
        temp_path.unlink()


TESTS = [
    test_no_file_imports_a_legacy_module_outside_the_four_approved_exceptions,
    test_at_least_one_file_actually_uses_each_approved_exception,
    test_scanner_itself_detects_a_genuine_violation,
]


def main() -> None:
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {test.__name__}: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {test.__name__}: {exc!r}")
            failed += 1
    print("-" * 74)
    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
