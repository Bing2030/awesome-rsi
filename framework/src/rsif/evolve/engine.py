"""EvolutionEngine: the trusted, frozen process running the improvement loop.

One generation = proposals_per_generation candidates, each through the five
phases (every event is phase-attributed):

  1. proposal     Improver proposes ONE bounded change (META template evolves)
  2. design       patch validated (bounds, operator) and materialized as
                  candidate versions - never activated
  3. exploration  cheap cascade screen on train-probe tasks; a candidate far
                  below its parent never reaches the expensive gates
  4. verification gate chain: static scan -> canary (never regress) ->
                  train -> val acceptance (child > parent + threshold)
  5. correction   accept: promote + archive; reject: reflection into episodic
                  memory, checkout stays at parent (candidate discarded)

Only evaluated improvements are kept [2505.22954, 2605.23904]; verification is
execution-grounded, never self-judged [2310.01798]; the archive preserves
niches and ancestry for backtracking [1504.04909].
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from rsif.artifacts.model import CreateOp, DeleteOp, Patch, RestoreOp, UpdateOp
from rsif.artifacts.store import ApplyResult, ArtifactError, ArtifactStore
from rsif.config import RunConfig
from rsif.evolve.archive import Archive, Individual
from rsif.evolve.assembler import build_spec
from rsif.evolve.operators import load_catalog, validate_operator
from rsif.evolve.proposer import Improver
from rsif.evolve.scheduler import schedule_for
from rsif.evolve.selection import accept_val, pass_canary, pass_screen
from rsif.llm.base import LLMProvider, ProviderError
from rsif.memory.episodic import ReflectionStore
from rsif.memory.insights import InsightStore
from rsif.objectives.base import Objective, ScoreBook, Split
from rsif.observe.events import (
    ACCEPT,
    APPROVAL,
    EventLog,
    ARCHIVE_UPDATE,
    BUDGET,
    ERROR,
    EVAL,
    GATE,
    LLM_CALL,
    META_CONFIRM,
    META_REVERT,
    PATCH,
    PROPOSAL,
    REJECT,
    REFLECT,
    ROLLBACK,
    RUN_END,
    RUN_START,
    SCREEN,
    PHASE_CORRECT,
    PHASE_DESIGN,
    PHASE_EXPLORE,
    PHASE_PROPOSE,
    PHASE_VERIFY,
)
from rsif.runtime.runtime import AgentRuntime
from rsif.safety.budget import Budget, BudgetExhausted
from rsif.safety.drift import STAGNATION, DriftMonitor
from rsif.safety.rollback import auto_rollback
from rsif.sandbox.guards import scan_code


@dataclass
class RunSummary:
    generations: int
    accepted: int
    rejected: int
    best_fitness: float | None
    best_descriptor: tuple | None
    best_snapshot: dict | None
    stop_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "generations": self.generations, "accepted": self.accepted,
            "rejected": self.rejected, "best_fitness": self.best_fitness,
            "best_descriptor": list(self.best_descriptor) if self.best_descriptor else None,
            "best_snapshot": self.best_snapshot,
            "stop_reason": self.stop_reason,
        }


class _EventfulProvider:
    """Wrap the LLM provider so every completion lands in the event log and
    the hard budget."""

    def __init__(self, inner: LLMProvider, events, budget: Budget | None = None):
        self.inner = inner
        self.events = events
        self.budget = budget

    def complete(self, req):
        try:
            result = self.inner.complete(req)
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001 - normalize SDK/connection errors
            raise ProviderError(str(e), origin=type(e).__name__) from e
        self.events.append(
            LLM_CALL, role=req.role, model=result.model,
            in_tokens=result.usage.in_tokens, out_tokens=result.usage.out_tokens,
        )
        if self.budget is not None:
            self.budget.record(result.usage.in_tokens, result.usage.out_tokens)
            overshot = self.budget.overshot()
            if overshot is not None:
                # a call past the hard limit aborts immediately: overshoot is
                # bounded by one call, not one proposal
                raise BudgetExhausted(overshot)
        return result


class EvolutionEngine:
    def __init__(self, *, store: ArtifactStore, provider: LLMProvider,
                 objective: Objective, cfg: RunConfig,
                 clock: Callable[[], float] = time.time, approver=None):
        self.store = store
        self.cfg = cfg
        self.objective = objective
        self.rng = random.Random(cfg.seed)
        self.events = EventLog(store.ws.events_path, clock=clock)
        self.budget = Budget(
            max_llm_calls=cfg.budget_llm_calls, max_usd=cfg.budget_usd,
            max_wall_s=cfg.budget_wall_clock_s)
        self.provider = _EventfulProvider(provider, self.events, self.budget)
        self.archive = Archive(store.ws.root / "archive.json")
        self.reflections = ReflectionStore(
            store.ws.memory_dir / "reflections.jsonl",
            max_entries=cfg.reflections_max, clock=clock)
        self.insights = InsightStore(store.ws.memory_dir / "insights.jsonl",
                                     clock=clock)
        self.runtime = AgentRuntime(
            self.provider,
            default_max_steps=cfg.max_steps_per_task,
            max_output_tokens=cfg.max_output_tokens,
            temperature=cfg.temperature, seed=cfg.seed)
        self.improver = Improver(self.provider, cfg)
        self.approver = approver  # None + required META edit => fail-closed deny
        self.drift: DriftMonitor | None = None  # wired after baseline
        self._eval_memo: dict[tuple, ScoreBook] = {}
        self._active_snapshot: dict[str, int] | None = None
        self._active_val: float = 0.0
        self._baseline_canary: float = 0.0
        self._consecutive_rejections = 0
        self._current_gen = 0  # generation context for mid-flight aborts
        self._outcomes: list[tuple[int, bool]] = []  # (generation, accepted)
        self._pending_meta: dict | None = None  # provisional META edit in window
        self.accepted = 0
        self.rejected = 0

    # -- entry ------------------------------------------------------------------

    def run(self, generations: int | None = None) -> RunSummary:
        generations = self.cfg.generations if generations is None else generations
        self.events.append(RUN_START, generation=0, generations=generations,
                           objective=self.cfg.objective, seed=self.cfg.seed)

        stop_reason: str | None = None
        self._current_gen = 0  # for mid-flight budget aborts (event context)
        try:
            root = self._baseline()
            self._active_snapshot = dict(root.spec_snapshot)
            self._active_val = root.val_score
            self.drift = DriftMonitor(
                baseline_canary=self._baseline_canary,
                stagnation_threshold=self.cfg.extra.get(
                    "stagnation_threshold",
                    max(4, 2 * self.cfg.proposals_per_generation)),
            )

            for gen in range(1, generations + 1):
                self._current_gen = gen
                for slot in range(self.cfg.proposals_per_generation):
                    dimension = self.budget.exhausted()
                    if dimension is not None:
                        self.events.append(BUDGET, generation=gen, dimension=dimension,
                                           budget=self.budget.snapshot())
                        stop_reason = f"budget:{dimension}"
                        break
                    self._one_proposal(gen, slot + 1, root)
                if stop_reason:
                    break
                if gen % self.cfg.insights_distill_every == 0:
                    self._retire_insights(gen)
                self._settle_meta(gen)
                if self._drift_check(gen):
                    stop_reason = "drift"
                    break
                self.archive.save(gen)
        except BudgetExhausted as e:
            # a single call pushed the run past the hard limit mid-proposal
            self.events.append(BUDGET, generation=self._current_gen,
                               dimension=e.dimension, budget=self.budget.snapshot())
            stop_reason = f"budget:{e.dimension}"
        except ProviderError as e:
            stop_reason = f"error:{e.origin}"
            # deterministic event payload: error type name only; the full
            # message (which may embed provider request ids / timestamps) is
            # surfaced to the caller, not written to the replay log.
            self.events.append(ERROR, generation=generations, error=e.origin)
        except Exception as e:  # noqa: BLE001 - engine bug: abort, never partial
            # provider errors are handled above; anything left is a bug in the
            # trusted engine itself and must not masquerade as a provider error
            stop_reason = f"engine:{type(e).__name__}"
            self.events.append(ERROR, generation=generations,
                               error=type(e).__name__)

        best = self.archive.best()
        payload = {"accepted": self.accepted, "rejected": self.rejected,
                   "best_fitness": best.fitness if best else None}
        if stop_reason:
            payload["stop_reason"] = stop_reason
        self.events.append(RUN_END, generation=generations, **payload)
        return RunSummary(
            generations=generations, accepted=self.accepted,
            rejected=self.rejected,
            best_fitness=best.fitness if best else None,
            best_descriptor=best.descriptor if best else None,
            best_snapshot=dict(best.spec_snapshot) if best else None,
            stop_reason=stop_reason,
        )

    # -- out-of-loop evaluation (CLI run / report) -------------------------------

    def evaluate_active(self, suite, label: str = "run") -> ScoreBook:
        """Evaluate the ACTIVE checkout on an arbitrary suite (rsif run).

        Reuses the exact evolve-time path (spec assembly, memory injection,
        memoization, persisted scorebooks, eval events), so scores are
        comparable across `evolve` and `run`.
        """
        return self._evaluate(self.store.snapshot(), suite, "", label, 0)

    def evaluate_snapshot(self, mapping: dict[str, int], suite,
                          label: str = "eval") -> ScoreBook:
        """Evaluate an arbitrary agent snapshot (rsif report: archive best)."""
        return self._evaluate(mapping, suite, "", label, 0)

    def _drift_check(self, gen: int) -> bool:
        """Generation-end misevolution check on the ACTIVE agent. Returns
        True if the run must stop."""
        assert self.drift is not None
        canary_book = self._evaluate(self._active_snapshot,
                                     self.objective.canaries(), "", "active", gen)
        best = self.archive.best()
        report = self.drift.check(
            active_val=self._active_val, active_canary=canary_book.mean(),
            best_val=best.fitness if best else self._active_val,
            consecutive_rejections=self._consecutive_rejections)
        if report.rollback_alarm:
            auto_rollback(self.store, self.archive, self.events, gen,
                          reason="+".join(report.alarms))
            if best is not None:
                self._active_snapshot = dict(best.spec_snapshot)
                self._active_val = best.fitness
            return False  # rolled back to a known-good agent; run continues
        if STAGNATION in report.alarms:
            approved = (self.approver.approve(
                f"drift:g{gen}", f"stagnation: {report.detail}")
                if self.approver is not None else False)
            self.events.append(
                APPROVAL, phase=PHASE_CORRECT, generation=gen,
                action="drift", alarms=report.alarms, detail=report.detail,
                approved=approved)
            return not approved
        return False

    # -- phase 0: baseline ------------------------------------------------------

    def _baseline(self) -> Individual:
        mapping = self.store.snapshot()
        suites = self.objective.suites()
        train_book = self._evaluate(mapping, suites[Split.TRAIN], "", "baseline", 0)
        canary_book = self._evaluate(mapping, suites[Split.CANARY], "", "baseline", 0)
        val_book = self._evaluate(mapping, suites[Split.VAL], "", "baseline", 0)
        val_score = self.objective.fitness(val_book)
        self._baseline_canary = canary_book.mean()
        ind = Individual(
            descriptor=("seed",) + tuple(self.objective.behavior_descriptors(val_book)),
            fitness=val_score, val_score=val_score,
            spec_snapshot=mapping, generation=0, proposal_id="seed")
        self.archive.add(ind)
        self.events.append(ARCHIVE_UPDATE, generation=0, action="baseline",
                           descriptor=list(ind.descriptor), fitness=ind.fitness)
        return ind

    # -- one proposal through all five phases -----------------------------------

    def _one_proposal(self, gen: int, slot: int, root: Individual) -> None:
        pid = f"g{gen}p{slot}"
        suites = self.objective.suites()
        parent = self.archive.sample_parent(self.rng) or root

        # -- phase 1: proposal -------------------------------------------------
        sched = schedule_for(gen, self.cfg.meta_every_k)
        try:
            proposal = self.improver.propose(
                self.store, self.archive, self._lessons_text(), parent,
                open_surfaces=set(sched.open_surfaces))
        except (ProviderError, BudgetExhausted):
            raise  # infrastructure failure, not a bad proposal: abort the run
        except Exception as e:  # noqa: BLE001 - improver output is untrusted
            self._reject(pid, gen, "parse", f"{type(e).__name__}: {e}", parent)
            return
        if not sched.is_open(proposal.surface.value):
            self._reject(pid, gen, "surface",
                         f"{proposal.surface.value!r} not open in generation "
                         f"{gen} (open: {sorted(sched.open_surfaces)})",
                         parent, proposal)
            return
        if (proposal.surface.value == "meta"
                and self.cfg.require_approval_for_meta):
            approved = self.approver.approve(
                pid, f"{proposal.operator}: {proposal.hypothesis}"
            ) if self.approver is not None else False
            self.events.append(
                APPROVAL, phase=PHASE_PROPOSE, generation=gen,
                proposal_id=pid, approved=approved)
            if not approved:
                self._reject(pid, gen, "approval",
                             "META edit not approved (fail-closed)",
                             parent, proposal)
                return
        self.events.append(
            PROPOSAL, phase=PHASE_PROPOSE, generation=gen, proposal_id=pid,
            surface=proposal.surface.value, operator=proposal.operator,
            hypothesis=proposal.hypothesis)

        # META edits run as controlled experiments: one at a time, each inside
        # its own evaluation window. A second META edit while one is pending
        # would confound whose proposals the window measured.
        meta_only = self._patch_is_meta_only(proposal.patch)
        if meta_only and self._pending_meta is not None:
            pend = self._pending_meta
            self._reject(
                pid, gen, "meta_pending",
                f"a META edit ({pend['proposal_id']}) is still inside its "
                f"eval window until generation "
                f"{pend['generation'] + pend['window']}", parent, proposal)
            return

        # -- phase 2: design (validate + materialize, no activation) ------------
        if len(proposal.patch.ops) > self.cfg.max_patch_ops:
            self._reject(pid, gen, "bounded",
                         f"{len(proposal.patch.ops)} ops > {self.cfg.max_patch_ops}",
                         parent, proposal)
            return
        catalog = load_catalog(self.store)
        if not validate_operator(catalog, proposal.operator, proposal.surface.value):
            self._reject(pid, gen, "operator",
                         f"operator {proposal.operator!r} not valid for surface "
                         f"{proposal.surface.value!r}", parent, proposal)
            return
        try:
            result = self.store.apply_patch(proposal.patch, proposal_id=pid,
                                            generation=gen)
        except ArtifactError as e:
            self._reject(pid, gen, "apply", str(e), parent, proposal)
            return
        candidate = {**parent.spec_snapshot, **result.versions}
        self.events.append(
            PATCH, phase=PHASE_DESIGN, generation=gen, proposal_id=pid,
            versions=result.versions, n_ops=len(proposal.patch.ops),
            rationale=proposal.rationale)

        # -- design feasibility gates (static, before ANY execution) -------------
        # a candidate that would escape the sandbox or cannot load must never
        # be evaluated, not even on the cheap screen [2603.03329 guard layers]
        violations = self._scan_patch(proposal.patch)
        self._gate(pid, gen, "scan", not violations,
                   phase=PHASE_DESIGN, violations=violations[:3])
        if violations:
            self._reject(pid, gen, "scan", "; ".join(violations[:3]),
                         parent, proposal)
            return

        # evolved architecture code must load and honor the module ABI before
        # it can be evaluated [2408.08435, 2410.04444]
        if self._patch_touches_module(proposal.patch):
            load_error = self._check_module_loads(candidate)
            self._gate(pid, gen, "load", load_error == "",
                       phase=PHASE_DESIGN, detail=load_error)
            if load_error:
                self._reject(pid, gen, "load", load_error, parent, proposal)
                return

        # -- phase 3: exploration (cheap cascade screen) -------------------------
        screen_suite = suites[Split.TRAIN].sample(self.cfg.screen_tasks, self.rng)
        child_screen = self._evaluate(candidate, screen_suite,
                                      PHASE_EXPLORE, "child", gen)
        parent_screen = self._evaluate(parent.spec_snapshot, screen_suite,
                                       PHASE_EXPLORE, "parent", gen)
        screen_ok = pass_screen(child_screen.mean(), parent_screen.mean(),
                                self.cfg.screen_epsilon)
        self.events.append(
            SCREEN, phase=PHASE_EXPLORE, generation=gen, proposal_id=pid,
            child=child_screen.mean(), parent=parent_screen.mean(),
            epsilon=self.cfg.screen_epsilon, passed=screen_ok)
        if not screen_ok:
            self._reject(pid, gen, "screen",
                         f"screen {child_screen.mean():.4f} < "
                         f"{parent_screen.mean():.4f} - {self.cfg.screen_epsilon}",
                         parent, proposal)
            return

        # -- phase 4: verification (execution-grounded gate chain) --------------
        canary_suite = self.objective.canaries()
        child_canary = self._evaluate(candidate, canary_suite,
                                      PHASE_VERIFY, "child", gen)
        parent_canary = self._evaluate(parent.spec_snapshot, canary_suite,
                                       PHASE_VERIFY, "parent", gen)
        canary_ok = pass_canary(child_canary.mean(), parent_canary.mean())
        self._gate(pid, gen, "canary", canary_ok,
                   child=child_canary.mean(), parent=parent_canary.mean())
        if not canary_ok:
            self._reject(pid, gen, "canary",
                         f"canary {child_canary.mean():.4f} < "
                         f"{parent_canary.mean():.4f}", parent, proposal)
            return

        # full train eval (memo-hits the screen when the screen covered the suite)
        child_train = self._evaluate(candidate, suites[Split.TRAIN],
                                     PHASE_VERIFY, "child", gen)

        child_val_book = self._evaluate(candidate, suites[Split.VAL],
                                        PHASE_VERIFY, "child", gen)
        parent_val_book = self._evaluate(parent.spec_snapshot, suites[Split.VAL],
                                         PHASE_VERIFY, "parent", gen)
        child_val = child_val_book.mean()
        parent_val = parent_val_book.mean()

        if meta_only:
            # A META-only patch leaves the agent spec byte-identical (META
            # artifacts are not part of AgentSpec), so the strict agent-val
            # gate measures only noise and can never fire. The empirical test
            # of a META edit is DEFERRED: accept on non-regression now, then
            # judge the improver by its proposals over meta_eval_window
            # generations (see _settle_meta). [2310.02304, 2309.16797]
            val_ok = child_val >= parent_val - 1e-9
            self._gate(pid, gen, "val", val_ok,
                       child=child_val, parent=parent_val,
                       detail="meta-only: agent unregressed; the improver "
                              "itself is judged over the eval window")
            if not val_ok:
                self._reject(pid, gen, "val",
                             f"meta-only edit regressed the agent: val "
                             f"{child_val:.4f} < {parent_val:.4f}",
                             parent, proposal)
                return
        else:
            child_scores = self._paired_scores(child_val_book, suites[Split.VAL])
            parent_scores = self._paired_scores(parent_val_book, suites[Split.VAL])
            val_ok = accept_val(child_val, parent_val,
                                self.cfg.acceptance_threshold,
                                child_scores, parent_scores)
            self._gate(pid, gen, "val", val_ok,
                       child=child_val, parent=parent_val,
                       threshold=self.cfg.acceptance_threshold,
                       detail=f"{child_val:.4f} > {parent_val:.4f} + "
                              f"{self.cfg.acceptance_threshold} "
                              f"(net task gain >= 1)")
            if not val_ok:
                self._reject(pid, gen, "val",
                             f"val {child_val:.4f} <= "
                             f"{parent_val:.4f} + "
                             f"{self.cfg.acceptance_threshold}", parent, proposal)
                return

        # -- phase 5: correction (two-level acceptance) ---------------------------
        # Archive-acceptance: the candidate beats ITS parent -> it enters its
        # MAP-Elites niche as a stepping stone [1504.04909, 1901.01753].
        # Promotion: it must also beat the ACTIVE agent -> the deployed agent
        # can never ratchet down through weak sampled parents.
        # A meta_only accept also deploys (the template), provisionally: it
        # changes the improver, not the agent, so the active agent's val is
        # untouched by construction.
        promoted = child_val > self._active_val or meta_only
        if promoted:
            self.store.promote(result, proposal_id=pid, generation=gen)
            self._active_snapshot = dict(candidate)
            if not meta_only:
                self._active_val = child_val
        self.accepted += 1
        self._consecutive_rejections = 0
        prior = [ok for _g, ok in self._outcomes]
        self._outcomes.append((gen, True))
        if meta_only:
            # open the eval window: remember the pre-edit META versions so a
            # failed window can revert, and the baseline success rate the
            # window must not fall below
            self._pending_meta = {
                "proposal_id": pid, "generation": gen,
                "window": self.cfg.meta_eval_window,
                "pre": {aid: parent.spec_snapshot.get(aid, 0)
                        for aid in result.versions},
                "baseline": (sum(prior) / len(prior)) if prior else None,
            }
        descriptor = (proposal.surface.value,) + tuple(
            self.objective.behavior_descriptors(child_val_book))
        ind = Individual(
            descriptor=descriptor, fitness=child_val,
            val_score=child_val, spec_snapshot=candidate,
            generation=gen, proposal_id=pid, parent_ref=parent.descriptor)
        stored = self.archive.add(ind)
        self.events.append(
            ACCEPT, phase=PHASE_CORRECT, generation=gen, proposal_id=pid,
            promoted=promoted, meta_provisional=meta_only,
            val_child=child_val, val_parent=parent_val_book.mean(),
            train_child=child_train.mean())
        self.events.append(
            ARCHIVE_UPDATE, phase=PHASE_CORRECT, generation=gen,
            action="candidate", proposal_id=pid, descriptor=list(descriptor),
            fitness=ind.fitness, stored=stored,
            active=self._active_val)
        # ExpeL-style distillation from the verified success [2308.10144]
        self.insights.distill([(
            pid, f"{proposal.hypothesis} (val {parent_val_book.mean():.2f} -> "
                 f"{child_val:.2f})")])
        self.events.append(
            REFLECT, phase=PHASE_CORRECT, generation=gen, action="distill_insight",
            proposal_id=pid)

    # -- META recursion: provisional acceptance + eval window -------------------

    def _patch_is_meta_only(self, patch: Patch) -> bool:
        """True iff every op touches META artifacts (agent spec unchanged).

        Mixed patches (META + an agent surface) take the normal strict val
        gate: the agent-visible part must pay for the whole patch.
        """
        if not patch.ops:
            return False
        for op in patch.ops:
            if isinstance(op, CreateOp):
                if op.type.value != "meta":
                    return False
            elif isinstance(op, (UpdateOp, DeleteOp, RestoreOp)):
                if self._safe_type_of(op.artifact_id) != "meta":
                    return False
            else:
                return False
        return True

    def _settle_meta(self, gen: int) -> None:
        """Close a pending META eval window: confirm, or revert the edit.

        A META-only edit was accepted provisionally on agent non-regression;
        the empirical question - did the IMPROVER improve? - is answerable
        only from the proposals it makes afterwards. If the window's proposal
        success rate falls below the pre-edit baseline (or produces zero wins
        where no baseline exists), the pre-edit META versions are restored
        (append-only lineage); otherwise the edit is confirmed. The improver's
        own evolution is thus itself empirically gated [2310.02304, 2309.16797].
        """
        p = self._pending_meta
        if p is None or gen < p["generation"] + p["window"]:
            return
        window = [ok for g, ok in self._outcomes if p["generation"] < g <= gen]
        rate = (sum(window) / len(window)) if window else 0.0
        if p["baseline"] is None:
            confirm = sum(window) > 0
        else:
            confirm = rate >= p["baseline"]
        pid = p["proposal_id"]
        span = [p["generation"] + 1, gen]
        if confirm:
            self._pending_meta = None
            self.events.append(
                META_CONFIRM, phase=PHASE_CORRECT, generation=gen,
                proposal_id=pid, window=span, success_rate=round(rate, 4),
                baseline=p["baseline"])
            return
        rid = f"meta-revert:{pid}"
        restored: dict[str, int] = {}
        for aid, version in sorted(p["pre"].items()):
            if version == 0:  # did not exist pre-edit: deactivate again
                self.store.delete(aid, proposal_id=rid, generation=gen)
                self.store.promote(ApplyResult({aid: 0}), proposal_id=rid,
                                   generation=gen)
            else:
                self.store.restore(aid, version, proposal_id=rid,
                                   generation=gen)
            restored[aid] = version
        if self._active_snapshot is not None:
            self._active_snapshot.update(p["pre"])
        self._pending_meta = None
        self.events.append(
            META_REVERT, phase=PHASE_CORRECT, generation=gen,
            proposal_id=pid, window=span, success_rate=round(rate, 4),
            baseline=p["baseline"], restored=restored)

    # -- correction helpers -------------------------------------------------------

    def _reject(self, pid: str, gen: int, reason: str, detail: str,
                parent: Individual, proposal=None) -> None:
        self.rejected += 1
        self._consecutive_rejections += 1
        self._outcomes.append((gen, False))
        self.events.append(
            REJECT, phase=PHASE_CORRECT, generation=gen, proposal_id=pid,
            reason=reason, detail=detail)
        # The candidate was never activated: the checkout stays at the parent.
        # Recorded as a rollback so the event log shows the discard explicitly.
        self.events.append(
            ROLLBACK, phase=PHASE_CORRECT, generation=gen, proposal_id=pid,
            action="discard_candidate",
            checkout_unchanged=True,
            parent_descriptor=list(parent.descriptor))
        # Reflexion: turn the rejection into a lesson for future proposals
        # [2303.11366]. Trace text is deterministic (ids + scores only).
        surface = proposal.surface.value if proposal else "?"
        operator = proposal.operator if proposal else "?"
        trace = (f"proposal {pid} [{surface}/{operator}] rejected at {reason}: "
                 f"{detail}. Parent fitness stays {parent.fitness:.4f}. "
                 f"Try a different, smaller change.")
        self.reflections.reflect(f"proposal/{pid}", trace, llm=self.provider,
                                 source=pid)
        self.events.append(
            REFLECT, phase=PHASE_CORRECT, generation=gen, proposal_id=pid,
            signature=f"proposal/{pid}")

    def _retire_insights(self, gen: int) -> None:
        retired = self.insights.retire_correlated()
        if retired:
            self.events.append(REFLECT, phase=PHASE_CORRECT, generation=gen,
                               action="retire_insights", count=len(retired))

    # -- evaluation -------------------------------------------------------------

    @staticmethod
    def _paired_scores(book: ScoreBook, suite) -> list[float]:
        """Per-task scores aligned to the suite's task order (paired gates)."""
        by_id = {s.task_id: s.score for s in book.scores}
        return [by_id[t.id] for t in suite.tasks]

    def _evaluate(self, mapping: dict[str, int], suite, phase: str,
                  label: str, generation: int) -> ScoreBook:
        key = (tuple(sorted(mapping.items())), suite.split.value,
               tuple(t.id for t in suite.tasks))
        if key not in self._eval_memo:
            book = ScoreBook()
            for task in suite.tasks:
                spec = build_spec(self.store, mapping,
                                  extra_memory=self._agent_memory(task.prompt))
                attempt = self.runtime.run(task.prompt, spec, role="agent")
                book.add(self.objective.evaluate(task, attempt))
            self._eval_memo[key] = book
            self._persist_scores(generation, label, suite, book)
            self.events.append(
                EVAL, phase=phase, generation=generation,
                suite=suite.split.value, label=label,
                n=len(suite.tasks), score=book.mean())
        return self._eval_memo[key]

    def _persist_scores(self, generation: int, label: str, suite,
                        book: ScoreBook) -> None:
        d = self.store.ws.eval_dir(generation)
        name = f"{suite.split.value}_{label}.json"
        (d / name).write_text(
            json.dumps({
                "mean": book.mean(),
                "scores": [{"task_id": s.task_id, "score": s.score}
                           for s in book.scores]}, indent=2, sort_keys=True),
            encoding="utf-8")

    def _agent_memory(self, task_prompt: str) -> str:
        insights = self.insights.render_for_context(task_prompt)
        reflections = self.reflections.render_for_context(task_prompt)
        return "\n".join(p for p in (insights, reflections) if p)

    def _lessons_text(self) -> str:
        insights = self.insights.render_for_context("agent improvement lessons")
        reflections = self.reflections.render_for_context("agent improvement lessons")
        return "\n".join(p for p in (insights, reflections) if p)

    def _scan_patch(self, patch: Patch) -> list[str]:
        violations: list[str] = []
        for op in patch.ops:
            if isinstance(op, CreateOp) and op.type.value in ("skill", "module"):
                violations += self._scan_payload(op.artifact_id, op.payload)
            elif isinstance(op, UpdateOp):
                try:
                    if self.store.type_of(op.artifact_id).value in ("skill", "module"):
                        violations += self._scan_payload(op.artifact_id, op.payload)
                except ArtifactError:
                    pass  # unknown artifact: the apply gate catches it
        return violations

    def _scan_payload(self, artifact_id: str, payload: dict[str, str]) -> list[str]:
        out = []
        for name, source in sorted(payload.items()):
            if name.endswith(".py"):
                report = scan_code(source)
                out += [f"{artifact_id}/{name}: {v}" for v in report.violations]
        return out

    def _safe_type_of(self, artifact_id: str) -> str | None:
        try:
            return self.store.type_of(artifact_id).value
        except ArtifactError:
            return None

    def _patch_touches_module(self, patch: Patch) -> bool:
        return any(
            (isinstance(op, CreateOp) and op.type.value == "module")
            or (isinstance(op, UpdateOp)
                and self._safe_type_of(op.artifact_id) == "module")
            for op in patch.ops)

    def _check_module_loads(self, candidate: dict[str, int]) -> str:
        """Empty string if the candidate's module code loads and honors the
        ABI; otherwise a description of why it cannot run."""
        from rsif.runtime.loader import ModuleLoadError, load_module_source

        try:
            spec = build_spec(self.store, candidate)
            load_module_source(spec.module_source)
            return ""
        except ModuleLoadError as e:
            return str(e)

    def _gate(self, pid: str, gen: int, gate: str, passed: bool,
              phase: str = PHASE_VERIFY, **payload) -> None:
        self.events.append(GATE, phase=phase, generation=gen,
                           proposal_id=pid, gate=gate, passed=passed, **payload)
