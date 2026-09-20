"""Run configuration.

Plain dataclass (no pydantic - the core is stdlib-only and the schemas are
internal); validation is explicit.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

PROVIDERS = ("scripted", "anthropic", "openai", "litellm")
OBJECTIVES = ("code-tasks", "exact-match")


class ConfigError(Exception):
    pass


@dataclass
class RunConfig:
    # identity / objective
    objective: str = "code-tasks"
    charter: str = "Improve task fitness through verified self-modification; never regress safety canaries."

    # LLM
    provider: str = "scripted"  # RSIF_PROVIDER env var overrides
    model: str = ""
    improver_model: str = ""  # empty = same as model
    temperature: float = 0.7
    seed: int = 0

    # agent runtime
    max_steps_per_task: int = 8
    max_output_tokens: int = 4096

    # evolution loop
    generations: int = 3
    proposals_per_generation: int = 2
    screen_tasks: int = 2  # cheap probe tasks per candidate (AlphaEvolve cascade)
    screen_epsilon: float = 0.30  # screen passes at >= parent - epsilon
    acceptance_threshold: float = 0.02  # val(child) > val(parent) + threshold
    meta_every_k: int = 3  # slow loop cadence for META artifacts
    meta_eval_window: int = 3  # generations a provisional META edit runs before confirm/revert
    max_patch_ops: int = 3  # bounded edits (ACE / SkillOpt discipline)
    max_playbook_sections: int = 12

    # safety
    budget_usd: float = 1.0
    budget_llm_calls: int = 2000
    budget_wall_clock_s: float = 3600.0
    require_approval_for_meta: bool = True
    sandbox_timeout_s: float = 10.0
    sandbox_mem_mb: int = 512

    # memory
    reflections_max: int = 50
    insights_distill_every: int = 3  # generations

    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise ConfigError(f"provider must be one of {PROVIDERS}, got {self.provider!r}")
        if self.objective not in OBJECTIVES:
            raise ConfigError(f"objective must be one of {OBJECTIVES}, got {self.objective!r}")
        if not 0.0 <= self.temperature <= 2.0:
            raise ConfigError("temperature out of range")
        if self.acceptance_threshold < 0:
            raise ConfigError("acceptance_threshold must be >= 0")

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict) -> "RunConfig":
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        cfg = cls(**kwargs)
        cfg.extra = {**(kwargs.get("extra") or {}),
                     **{k: v for k, v in data.items() if k not in known}}
        return cfg

    def resolved_model(self, role: str = "agent") -> str:
        if role == "improver" and self.improver_model:
            return self.improver_model
        return self.model
