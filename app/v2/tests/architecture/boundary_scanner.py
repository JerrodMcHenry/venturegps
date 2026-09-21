"""
Static scanner enforcing the V2 AI/determinism boundary (rules: boundary_rules.py).

Pure AST analysis: it never imports or executes the code it scans, needs no
database, no network and no credentials.

Rule names (Violation.rule):

  deterministic-imports-ai          deterministic code imports app.v2.ai
  deterministic-imports-provider-sdk  ... imports openai/anthropic/tavily/...
  deterministic-imports-legacy      ... imports a legacy app.* module
  deterministic-references-ai-env   ... names OPENAI_API_KEY & friends
  ai-imports-persistence            app.v2.ai imports a DB driver/ORM, or a
                                    V2 repository/db/worker package
  ai-imports-disallowed-v2-package  app.v2.ai imports a V2 package outside its allowlist
  ai-imports-legacy                 app.v2.ai imports a legacy app.* module
  pure-imports-forbidden            a pure package (app.v2.domain / app.v2.observations)
                                    imports a database, SQL, network, process, config
                                    or persistence module
  pure-imports-disallowed-v2-package  a pure package imports a V2 package outside the pure ones
  pure-reads-environment            a pure package mentions environ/getenv/...
  network-import-forbidden          ingestion/repositories/candidates import a network, socket or DNS module
  candidate-layer-imports-canonical the candidate layer imports a (future) resolution/promotion/canonical package
  deterministic-imports-worker-framework  deterministic code imports a worker/queue/scheduler framework
  layer-violation                   a lower layer imports one built on it
  dynamic-import-unresolvable       importlib.import_module(x)/__import__(x)
                                    with a non-constant or relative argument
  unparseable-source                file cannot be parsed (fail closed)

`from pkg import name` is checked as BOTH `pkg` and `pkg.name`, because
`from app.v2 import ai` imports the app.v2.ai submodule.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.v2.tests.architecture.boundary_rules import (
    DEFAULT_RULES,
    BoundaryRules,
    matches_prefix,
)

REPO_ROOT = Path(__file__).resolve().parents[4]

ZONE_AI = "ai"
ZONE_WIRING = "wiring"
ZONE_DETERMINISTIC = "deterministic"


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    lineno: int
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.lineno} [{self.rule}] {self.detail}"


@dataclass(frozen=True)
class ImportRef:
    name: str | None  # None => dynamic/unresolvable
    lineno: int
    detail: str = ""


@dataclass
class ScanResult:
    files_scanned: list[str] = field(default_factory=list)
    modules_by_zone: dict[str, list[str]] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)


# ---------------------------------------------------------------- zoning


def module_name_for(rel_path: str) -> tuple[str, bool] | None:
    """('app.v2.domain.x', is_package) for a repo-relative .py path."""
    path = PurePosixPath(rel_path)
    if path.suffix != ".py":
        return None
    parts = list(path.with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def zone_for_module(module: str, rules: BoundaryRules = DEFAULT_RULES) -> str | None:
    if not matches_prefix(module, [rules.v2_root]):
        return None
    if matches_prefix(module, rules.excluded_packages):
        return None
    if matches_prefix(module, [rules.ai_package]):
        return ZONE_AI
    if module in rules.wiring_modules:
        return ZONE_WIRING
    return ZONE_DETERMINISTIC


def zone_for_path(rel_path: str, rules: BoundaryRules = DEFAULT_RULES) -> str | None:
    info = module_name_for(rel_path)
    return None if info is None else zone_for_module(info[0], rules)


# ------------------------------------------------------- name predicates


def is_provider_sdk(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    if matches_prefix(name, rules.provider_sdk_prefixes):
        return True
    top = name.split(".", 1)[0]
    return any(top.startswith(start) for start in rules.provider_sdk_toplevel_starts)


def is_legacy(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    """A legacy app.* module (or bare `app`), excluding V2 and the allowlist."""
    if name != "app" and not name.startswith("app."):
        return False
    if matches_prefix(name, [rules.v2_root]):
        return False
    return not matches_prefix(name, rules.legacy_import_allowlist)


def is_v2(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    return matches_prefix(name, [rules.v2_root])


def is_allowed_v2_for_ai(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    if name == rules.v2_root:
        return True
    if matches_prefix(name, rules.ai_allowed_v2_imports):
        return True
    # ancestor of an allowed entry (e.g. app.v2.resolution for ...resolution.ports)
    return any(entry.startswith(name + ".") for entry in rules.ai_allowed_v2_imports)


def is_pure_module(module: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    return matches_prefix(module, rules.pure_packages)


def is_allowed_v2_for_pure(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    return name == rules.v2_root or matches_prefix(name, rules.pure_allowed_v2_imports)


def is_no_network_module(module: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    return matches_prefix(module, rules.no_network_packages)


def is_forbidden_loaded_for_network(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    """Runtime probe on sys.modules after importing a no-network module."""
    return matches_prefix(name, rules.network_forbidden_loaded_prefixes) or is_forbidden_loaded_for_deterministic(name, rules)


def is_forbidden_loaded_for_pure(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    """Runtime probe on sys.modules after importing pure modules."""
    return matches_prefix(name, rules.pure_forbidden_loaded_prefixes) or is_forbidden_loaded_for_deterministic(name, rules)


def is_forbidden_loaded_for_deterministic(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    """Used by the runtime probe on sys.modules of a deterministic import."""
    if name == "app":
        return False
    return (
        matches_prefix(name, [rules.ai_package])
        or is_provider_sdk(name, rules)
        or is_legacy(name, rules)
    )


def is_forbidden_loaded_for_ai(name: str, rules: BoundaryRules = DEFAULT_RULES) -> bool:
    """Used by the runtime probe on sys.modules of an app.v2.ai import."""
    if name == "app":
        return False
    if matches_prefix(name, rules.ai_forbidden_import_prefixes) or is_legacy(name, rules):
        return True
    return is_v2(name, rules) and not is_allowed_v2_for_ai(name, rules)


# ------------------------------------------------------ import extraction


def _resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str | None:
    package = module if is_package else module.rpartition(".")[0]
    parts = package.split(".") if package else []
    drop = level - 1
    if drop >= len(parts):
        return None
    base = ".".join(parts[: len(parts) - drop])
    return f"{base}.{target}" if target else base


_DYNAMIC_IMPORT_CALLS = {"__import__", "import_module"}


def extract_imports(tree: ast.AST, module: str, is_package: bool) -> list[ImportRef]:
    refs: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            refs.extend(ImportRef(alias.name, node.lineno) for alias in node.names)

        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module
            else:
                base = _resolve_relative(module, is_package, node.level, node.module)
            if base is None:
                refs.append(ImportRef(None, node.lineno, "relative import escapes the package root"))
                continue
            refs.append(ImportRef(base, node.lineno))
            refs.extend(
                ImportRef(f"{base}.{alias.name}", node.lineno)
                for alias in node.names
                if alias.name != "*"
            )

        elif isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if called in _DYNAMIC_IMPORT_CALLS:
                arg = node.args[0] if node.args else None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and not arg.value.startswith("."):
                    refs.append(ImportRef(arg.value, node.lineno, f"{called}(...)"))
                else:
                    refs.append(ImportRef(None, node.lineno, f"{called}(...) with a non-constant or relative argument"))
    return refs


# ------------------------------------------------------- env-name scanning


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ids.add(id(value))
    return ids


def _texts_in(tree: ast.AST):
    """(text, lineno) for every string constant and identifier-like name.
    Docstrings are exempt (documentation, not behavior)."""
    docstrings = _docstring_node_ids(tree)
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                yield node.value, lineno
        elif isinstance(node, ast.Name):
            yield node.id, lineno
        elif isinstance(node, ast.Attribute):
            yield node.attr, lineno
        elif isinstance(node, ast.arg):
            yield node.arg, lineno
        elif isinstance(node, ast.keyword):
            if node.arg:
                yield node.arg, getattr(node.value, "lineno", lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name, lineno
        elif isinstance(node, ast.alias):
            yield node.name, lineno
            if node.asname:
                yield node.asname, lineno


def _env_violations(tree: ast.AST, rel_path: str, rules: BoundaryRules) -> list[Violation]:
    found: dict[tuple[int, str], Violation] = {}
    for text, lineno in _texts_in(tree):
        lowered = text.lower()
        for env_name in rules.forbidden_env_names:
            if env_name.lower() in lowered:
                found.setdefault(
                    (lineno, env_name),
                    Violation(
                        "deterministic-references-ai-env",
                        rel_path,
                        lineno,
                        f"deterministic code references {env_name}",
                    ),
                )
    return list(found.values())


def _pure_name_violations(tree: ast.AST, rel_path: str, rules: BoundaryRules) -> list[Violation]:
    found: dict[tuple[int, str], Violation] = {}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.alias):
            names.append(node.name.rsplit(".", 1)[-1])
        for name in names:
            if name in rules.pure_forbidden_names:
                lineno = getattr(node, "lineno", 0)
                found.setdefault(
                    (lineno, name),
                    Violation("pure-reads-environment", rel_path, lineno, f"pure module mentions {name}"),
                )
    return list(found.values())


# ----------------------------------------------------------- rule checks


def _check_import(ref: ImportRef, zone: str, rel_path: str, rules: BoundaryRules, module: str = "") -> list[Violation]:
    def violation(rule: str, detail: str) -> Violation:
        return Violation(rule, rel_path, ref.lineno, detail)

    if ref.name is None:
        return [violation("dynamic-import-unresolvable", ref.detail)]

    name = ref.name
    out: list[Violation] = []

    if zone in (ZONE_DETERMINISTIC, ZONE_WIRING):
        if matches_prefix(name, rules.worker_framework_prefixes):
            out.append(violation("deterministic-imports-worker-framework", f"imports {name}"))
        if zone == ZONE_DETERMINISTIC and matches_prefix(name, [rules.ai_package]):
            out.append(violation("deterministic-imports-ai", f"imports {name}"))
        if is_provider_sdk(name, rules):
            out.append(violation("deterministic-imports-provider-sdk", f"imports {name}"))
        if is_legacy(name, rules):
            out.append(violation("deterministic-imports-legacy", f"imports legacy module {name}"))

        if module and is_pure_module(module, rules):
            if matches_prefix(name, rules.pure_forbidden_import_prefixes):
                out.append(violation("pure-imports-forbidden", f"pure module imports {name}"))
            elif is_v2(name, rules) and not is_allowed_v2_for_pure(name, rules) and not matches_prefix(name, rules.pure_forbidden_import_prefixes):
                out.append(violation("pure-imports-disallowed-v2-package", f"pure module imports {name}"))
        if module and matches_prefix(module, rules.candidate_layer_packages) and matches_prefix(name, rules.canonical_forbidden_import_prefixes):
            out.append(violation("candidate-layer-imports-canonical", f"{module} must not import {name}"))
        if module and is_no_network_module(module, rules) and matches_prefix(name, rules.network_forbidden_import_prefixes):
            out.append(violation("network-import-forbidden", f"{module} must not import {name}"))
        for package, forbidden in rules.layer_rules:
            if module and matches_prefix(module, [package]) and matches_prefix(name, forbidden):
                out.append(violation("layer-violation", f"{package} must not import {name}"))

    elif zone == ZONE_AI:
        if matches_prefix(name, rules.ai_forbidden_import_prefixes):
            out.append(violation("ai-imports-persistence", f"app.v2.ai imports {name}"))
        elif is_legacy(name, rules):
            out.append(violation("ai-imports-legacy", f"app.v2.ai imports legacy module {name}"))
        elif is_v2(name, rules) and not is_allowed_v2_for_ai(name, rules):
            out.append(violation("ai-imports-disallowed-v2-package", f"app.v2.ai imports {name}"))

    return out


# --------------------------------------------------------------- scanning


def scan_source(source: str, rel_path: str, rules: BoundaryRules = DEFAULT_RULES) -> list[Violation]:
    """Scan one file's source as if it lived at repo-relative rel_path."""
    info = module_name_for(rel_path)
    if info is None:
        return []
    module, is_package = info
    zone = zone_for_module(module, rules)
    if zone is None:
        return []

    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as exc:
        return [Violation("unparseable-source", rel_path, exc.lineno or 0, f"cannot verify: {exc.msg}")]

    violations: list[Violation] = []
    for ref in extract_imports(tree, module, is_package):
        violations.extend(_check_import(ref, zone, rel_path, rules, module))
    if zone != ZONE_AI:
        violations.extend(_env_violations(tree, rel_path, rules))
    if is_pure_module(module, rules):
        violations.extend(_pure_name_violations(tree, rel_path, rules))
    return violations


def scan_tree(root: Path = REPO_ROOT, rules: BoundaryRules = DEFAULT_RULES) -> ScanResult:
    """Scan every .py under <root>/app/v2 (tests excluded by zone)."""
    result = ScanResult()
    v2_dir = root.joinpath(*rules.v2_root.split("."))
    if not v2_dir.is_dir():
        return result

    for path in sorted(v2_dir.rglob("*.py")):
        rel_path = path.relative_to(root).as_posix()
        info = module_name_for(rel_path)
        zone = zone_for_module(info[0], rules) if info else None
        if zone is None:
            continue
        result.files_scanned.append(rel_path)
        result.modules_by_zone.setdefault(zone, []).append(info[0])
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            result.violations.append(Violation("unparseable-source", rel_path, 0, f"not valid UTF-8: {exc}"))
            continue
        result.violations.extend(scan_source(source, rel_path, rules))
    return result
