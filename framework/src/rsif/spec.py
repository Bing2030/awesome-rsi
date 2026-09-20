"""AgentSpec: the resolved active agent, assembled from the checkout.

The runtime interprets the spec; the spec evolves. Context composition is:
system prompt artifact + retrieved skills + retrieved insights/reflections,
per Voyager skill retrieval [2305.16291], Reflexion [2303.11366] and ExpeL
[2308.10144] memory retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillSpec:
    name: str
    description: str
    code: str


@dataclass
class AgentSpec:
    system_prompt: str = ""
    skills: list[SkillSpec] = field(default_factory=list)
    memory: str = ""  # retrieved insights + reflections text
    module_source: str = ""
    module_path: str = ""  # optional: absolute path of the module version dir

    def compose_system(self) -> str:
        parts = [self.system_prompt]
        if self.skills:
            parts.append("\n## Available skills\n" + "\n".join(
                f"- {s.name}: {s.description}" for s in self.skills))
        if self.memory:
            parts.append("\n## Memory / lessons\n" + self.memory)
        return "\n\n".join(p for p in parts if p)
