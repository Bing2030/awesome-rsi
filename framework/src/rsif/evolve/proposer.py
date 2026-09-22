"""The Improver: the meta-agent that proposes one bounded change per call.

The improver's prompt is assembled from the *active* improver template (a
META artifact - so the improver's own strategy evolves), the current checkout
summary, the archive frontier + superseded lineages, and recent lessons
(reflections + insights). Its response is parsed into a Proposal.

Grounding: STOP improver [arXiv 2310.02304]; Promptbreeder task + mutation
prompts [arXiv 2309.16797]; DGM self-modification via LLM [arXiv 2505.22954].
"""

from __future__ import annotations

from rsif.artifacts.store import ArtifactStore
from rsif.config import RunConfig
from rsif.evolve.archive import Archive, Individual
from rsif.evolve.operators import OP_SCHEMA, load_catalog, render_operators
from rsif.evolve.proposal import Proposal, parse_proposal
from rsif.llm.base import CompletionRequest, LLMProvider, Message

IMPROVER_SYSTEM = (
    "You are the Improver, a meta-agent that makes an agent better by "
    "proposing ONE bounded, testable change per call. Respond with a single "
    "JSON object and nothing else."
)

_IMPROVER_ROLE = "improver"


class Improver:
    def __init__(self, provider: LLMProvider, cfg: RunConfig,
                 template_id: str = "meta/improver-template"):
        from rsif.constants import IMPROVER_TEMPLATE_ID

        self.provider = provider
        self.cfg = cfg
        self.template_id = template_id or IMPROVER_TEMPLATE_ID

    # -- prompt assembly ------------------------------------------------------

    def build_prompt(self, store: ArtifactStore, archive: Archive,
                     lessons: str, parent: Individual,
                     open_surfaces: set[str] | None = None,
                     gaps: str = "") -> tuple[str, str]:
        template = self._template(store)
        catalog = load_catalog(store)
        user = template.format(
            max_ops=self.cfg.max_patch_ops,
            checkout_summary=self._checkout_summary(store),
            archive_summary=self._archive_summary(archive, parent),
            gaps=gaps or "(none recorded)",
            lessons=lessons or "(none yet)",
            operators=render_operators(catalog, surfaces=open_surfaces),
            op_schema=OP_SCHEMA,
        )
        return IMPROVER_SYSTEM, user

    def _template(self, store: ArtifactStore) -> str:
        payload = store.read_active(self.template_id)
        for name in ("template.md", "improver.md"):
            if name in payload:
                return payload[name]
        return next(iter(payload.values()), "")

    def _checkout_summary(self, store: ArtifactStore) -> str:
        lines = []
        for aid, version in sorted(store.checkout().items()):
            try:
                atype = store.type_of(aid).value
                payload = store.read_version(aid, version)
                preview = next(iter(payload.values()), "")[:80].replace("\n", " ")
            except Exception:  # noqa: BLE001 - summary must never crash the loop
                preview = "(unreadable)"
                atype = "?"
            lines.append(f"- {aid} v{version} ({atype}): {preview}")
        return "\n".join(lines) if lines else "(empty checkout)"

    def _archive_summary(self, archive: Archive, parent: Individual) -> str:
        lines = []
        for ind in archive.frontier()[:5]:
            lines.append(f"- {'/'.join(str(d) for d in ind.descriptor)}: "
                         f"fitness={ind.fitness:.4f} gen={ind.generation} "
                         f"proposal={ind.proposal_id or 'seed'}")
        superseded = archive.superseded_individuals()
        if superseded:
            revisit = ['/'.join(str(d) for d in i.descriptor)
                       for i in superseded[-5:]]
            lines.append(f"superseded lineages worth revisiting: {revisit}")
        lines.append(f"parent to mutate: "
                     f"{'/'.join(str(d) for d in parent.descriptor)} "
                     f"(fitness={parent.fitness:.4f})")
        return "\n".join(lines) if lines else "(empty archive)"

    # -- proposal -------------------------------------------------------------

    def propose(self, store: ArtifactStore, archive: Archive, lessons: str,
                parent: Individual,
                open_surfaces: set[str] | None = None,
                gaps: str = "") -> Proposal:
        system, user = self.build_prompt(store, archive, lessons, parent,
                                         open_surfaces, gaps)
        req = CompletionRequest(
            messages=(Message("system", system), Message("user", user)),
            model=self.cfg.resolved_model(_IMPROVER_ROLE),
            temperature=self.cfg.temperature,
            seed=self.cfg.seed,
            max_tokens=self.cfg.max_output_tokens,
            role=_IMPROVER_ROLE,
        )
        result = self.provider.complete(req)
        return parse_proposal(result.text)
