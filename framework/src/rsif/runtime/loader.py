"""Load an architecture module from an immutable artifact version dir.

Validates the ABI (a `Module` class subclassing AgentModule) and statically
scans the source for forbidden constructs before import. The module sees only
ModuleContext at runtime - never the store/engine/sandbox policy.

Grounding: architecture evolution within a fixed envelope [arXiv 2408.08435,
2410.04444]; guard layers before execution [arXiv 2603.03329].
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from rsif.runtime.module_api import AgentModule
from rsif.sandbox.guards import scan_code


class ModuleLoadError(Exception):
    pass


def load_module_source(source: str, name: str = "agent_module") -> type[AgentModule]:
    report = scan_code(source)
    if not report.safe:
        raise ModuleLoadError("forbidden constructs: " + "; ".join(report.violations))

    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(name, loader=None))
    sys.modules[name] = module
    try:
        exec(compile(source, f"<{name}>", "exec"), module.__dict__)
    except Exception as e:  # noqa: BLE001 - surface the agent's error clearly
        raise ModuleLoadError(f"import failed: {e}") from e
    finally:
        sys.modules.pop(name, None)

    for attr in dir(module):
        obj = getattr(module, attr)
        if (isinstance(obj, type) and issubclass(obj, AgentModule)
                and obj is not AgentModule):
            return obj
    raise ModuleLoadError("no Module class (subclass of AgentModule) found")


def load_module_from_dir(path: Path, name: str = "agent_module") -> type[AgentModule]:
    py = Path(path) / "module.py"
    if not py.exists():
        raise ModuleLoadError(f"no module.py in {path}")
    return load_module_source(py.read_text(encoding="utf-8"), name=name)
