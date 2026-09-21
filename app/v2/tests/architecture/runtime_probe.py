"""
Runtime complement to the static scanner.

Imports modules in a FRESH subprocess (clean interpreter, AI credentials
stripped from the environment) and reports which modules ended up in
sys.modules. Unlike the AST scan this sees transitive imports, but it only
proves what the imported code did on import.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.v2.tests.architecture.boundary_rules import DEFAULT_RULES

_MARKER = "PROBE_RESULT:"

_SCRIPT = """
import importlib, json, sys
failed = {}
for name in json.loads(sys.argv[1]):
    try:
        importlib.import_module(name)
    except BaseException as exc:
        failed[name] = type(exc).__name__ + ": " + str(exc)
print("%s" + json.dumps({"failed": failed, "loaded": sorted(sys.modules)}))
""" % _MARKER


@dataclass(frozen=True)
class ProbeResult:
    failed: dict[str, str]
    loaded: list[str]


def run_import_probe(modules: list[str], cwd: Path, pythonpath: Path | None = None) -> ProbeResult:
    env = {k: v for k, v in os.environ.items() if k not in DEFAULT_RULES.forbidden_env_names}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)

    completed = subprocess.run(
        [sys.executable, "-c", _SCRIPT, json.dumps(modules)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise AssertionError(f"probe subprocess crashed:\n{completed.stderr}")

    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(_MARKER):
            payload = json.loads(line[len(_MARKER):])
            return ProbeResult(failed=payload["failed"], loaded=payload["loaded"])
    raise AssertionError(f"probe produced no result:\n{completed.stdout}\n{completed.stderr}")
