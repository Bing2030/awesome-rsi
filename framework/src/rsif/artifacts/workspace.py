"""Run workspace: the on-disk layout of one evolution run.

    <run>/
      config.json        run configuration (RunConfig)
      seed.json          RNG seed + clock mode, for deterministic replay
      events.jsonl       append-only event log (observe.events)
      lineage.jsonl      append-only artifact lineage (artifacts.store)
      artifacts/<id>/vN/ immutable artifact version dirs
      checkout.json      the active agent: artifact_id -> version mapping
      evals/<gen>/       per-candidate scorebooks + traces
      cache/llm/         provider response cache
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(Exception):
    pass


@dataclass
class RunWorkspace:
    root: Path

    # -- construction ------------------------------------------------------

    @classmethod
    def init(cls, root: Path | str, config: dict, seed: int) -> "RunWorkspace":
        root = Path(root).resolve()
        if root.exists() and any(root.iterdir()):
            raise WorkspaceError(f"workspace not empty: {root}")
        ws = cls(root)
        for d in (ws.artifacts_dir, ws.evals_dir, ws.cache_dir, ws.memory_dir):
            d.mkdir(parents=True, exist_ok=True)
        ws.config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        ws.seed_path.write_text(json.dumps({"seed": seed}, indent=2), encoding="utf-8")
        ws.checkout_path.write_text("{}", encoding="utf-8")
        ws.events_path.write_text("", encoding="utf-8")
        ws.lineage_path.write_text("", encoding="utf-8")
        return ws

    @classmethod
    def open(cls, root: Path | str) -> "RunWorkspace":
        root = Path(root).resolve()
        ws = cls(root)
        if not ws.config_path.exists():
            raise WorkspaceError(f"not a rsif workspace: {root}")
        return ws

    # -- paths -------------------------------------------------------------

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def seed_path(self) -> Path:
        return self.root / "seed.json"

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def lineage_path(self) -> Path:
        return self.root / "lineage.jsonl"

    @property
    def checkout_path(self) -> Path:
        return self.root / "checkout.json"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    @property
    def evals_dir(self) -> Path:
        return self.root / "evals"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    def eval_dir(self, generation: int) -> Path:
        d = self.evals_dir / f"gen_{generation:04d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -- helpers -----------------------------------------------------------

    def config(self) -> dict:
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def seed(self) -> int:
        return int(json.loads(self.seed_path.read_text(encoding="utf-8"))["seed"])
