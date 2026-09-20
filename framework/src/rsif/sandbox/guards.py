"""Static AST scan for forbidden constructs, before any execution.

Defense in depth [AutoHarness 2603.03329 guard layers; DGM bug-catching
2505.22954]: reject code that would escape the sandbox before we run it.
The scan is advisory-but-authoritative for MODULE/SKILL artifacts - the
runtime still runs everything in the subprocess sandbox, but the scan gives
a cheap, explainable early rejection.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

FORBIDDEN_IMPORTS = {
    "subprocess", "socket", "os", "shutil", "ctypes", "signal", "multiprocessing",
    "pickle", "sys",  # sys is fine in the agent's code but blocked for module/skill
}

# Importing the framework's own trusted internals from an evolved artifact is
# forbidden: modules see only ModuleContext, never the store/engine/sandbox.
FORBIDDEN_IMPORT_PREFIXES = ("rsif.artifacts", "rsif.evolve", "rsif.safety",
                             "rsif.observe")


@dataclass
class ScanReport:
    safe: bool
    violations: list[str]


def scan_code(source: str) -> ScanReport:
    violations: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ScanReport(False, [f"syntax error: {e}"])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_import(alias.name, node.lineno, violations)
        elif isinstance(node, ast.ImportFrom):
            _check_import(node.module or "", node.lineno, violations)
    return ScanReport(len(violations) == 0, violations)


def _check_import(name: str, lineno: int, violations: list[str]) -> None:
    top = name.split(".")[0]
    if top in FORBIDDEN_IMPORTS:
        violations.append(f"line {lineno}: forbidden import {name!r}")
    for prefix in FORBIDDEN_IMPORT_PREFIXES:
        if name == prefix or name.startswith(prefix + "."):
            violations.append(f"line {lineno}: forbidden framework import {name!r}")
