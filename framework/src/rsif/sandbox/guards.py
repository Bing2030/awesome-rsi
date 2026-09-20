"""Static AST scan for evolved code, before any execution.

Defense in depth [AutoHarness 2603.03329 guard layers; DGM bug-catching
2505.22954]: reject code that would escape policy before we run it.

The scan is a WHITELIST, not a blacklist: a blacklist of forbidden modules is
bypassable via transitive imports (`from rsif.commands import os` imports the
trusted CLI module and binds its `os` attribute). Evolved code may import a
curated set of pure-stdlib modules plus exactly one framework module - the
module ABI - and nothing else.

Threat-model honesty: MODULE code is exec'd in-process (it must implement the
runtime ABI in the engine process), so this scan is the primary barrier for
the architecture surface; SKILL code runs in the subprocess sandbox
(`sandbox/exec.py`), where the scan is an early, explainable rejection ahead
of the sandbox's own limits.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# Pure / deterministic-enough stdlib modules evolved code may use. Anything
# touching the OS, processes, network, or the interpreter itself is absent.
ALLOWED_STDLIB = {
    "abc", "ast", "bisect", "collections", "copy", "dataclasses", "datetime",
    "decimal", "difflib", "enum", "fractions", "functools", "hashlib",
    "heapq", "itertools", "json", "math", "numbers", "operator", "pprint",
    "random", "re", "statistics", "string", "textwrap", "time", "typing",
    "unicodedata", "uuid",
}

# The single framework import evolved code needs: the module ABI envelope.
ALLOWED_RSIF = ("rsif.runtime.module_api",)


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
    if name.startswith("rsif."):
        if name not in ALLOWED_RSIF:
            violations.append(
                f"line {lineno}: framework import {name!r} not allowed "
                f"(only {ALLOWED_RSIF[0]})")
        return
    if name == "rsif":
        violations.append(f"line {lineno}: framework import {name!r} not allowed")
        return
    top = name.split(".")[0]
    if top not in ALLOWED_STDLIB:
        violations.append(
            f"line {lineno}: import {name!r} not in the evolved-code whitelist")
