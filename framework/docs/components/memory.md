# Component guide — memory

*Three layers with different lifecycles: what failed (episodic), what was
verified to work (distilled), and what the agent currently knows (playbook).*

Files: `src/rsif/memory/{episodic,insights,playbook,retrieve}.py`. Verified
by `tests/unit/test_memory.py`. Injection path: `engine._agent_memory` +
`build_spec(extra_memory=…)` (see [runtime.md](runtime.md)).

## The three layers

| Layer | Store | Written when | Retrieved | Grounding |
|---|---|---|---|---|
| **Reflections** (episodic) | `memory/reflections.jsonl` | every rejection (`engine._reject`) | per task / per improver call, TF-IDF top-3 | Reflexion [2303.11366] |
| **Insights** (distilled) | `memory/insights.jsonl` | every *verified acceptance* (`insights.distill`), retired periodically | same | ExpeL [2308.10144] |
| **Playbook** (curated context) | the `memory/playbook` **artifact** | only through bounded, acceptance-gated patches | always (it *is* the artifact) | ACE [2510.04618] |

The asymmetry is deliberate: failures produce reflections immediately and
cheaply; successes must pass the full gate chain before anything is
distilled. Nothing enters long-term memory on the model's say-so.

## Reflections (`episodic.py`)

- `reflect(task_signature, trace_text, llm=None, source=…)` — if an LLM is
  available it generates the lesson from the trace; otherwise the
  deterministic trace text is stored (the golden path: ids + scores only).
- Every reflection has a `source` proposal id; the engine's traces are
  deterministic, so replays reproduce memory exactly.
- `render_for_context(query, top_k=3)` — TF-IDF-ranked retrieval, rendered
  as bullet lines.
- Ring buffer, capped at `reflections_max` (default 50).

In the flagship run, proposal B's val rejection produces the reflection
that (retrieved into the next improver call) shapes subsequent proposals —
the feed-forward loop is visible in the event log (`reflect` after each
`reject`).

## Insights (`insights.py`)

- `distill([(proposal_id, text)])` — called by the engine on acceptance
  with a one-line verified fact ("adding an edge-case checklist (val 0.40 →
  0.80)"). Carries `provenance` (proposal ids).
- `record_failure(indices)` — an insight that was injected and the run
  still failed; failures accumulate per insight.
- `retire_correlated(threshold=2)` — insights that co-occur with repeated
  failures are retired. Run by the engine every `insights_distill_every`
  (default 3) generations; emits `reflect(action="retire_insights")`.
- `render_for_context(query, top_k=3)` — same retrieval as reflections.

This is the hallucination guard: distillation is restricted to verified
successes and usage is tracked, so bad lessons age out instead of
compounding (model-collapse findings [2510.16657]).

## Playbook (`playbook.py`)

The structured part of the agent's standing context, stored as the
`memory/playbook` artifact — a JSON list of `{id, title, body}` sections:

```json
[{"id": "s1", "title": "General strategy",
  "body": "Read the task carefully; implement exactly the requested
           signature; keep code simple and stdlib-only."}]
```

- `PlaybookEditor` enforces bounded edits: ≤ `max_ops_per_patch` ops and ≤
  `max_sections` total (default 12). Unbounded rewrites raise — the
  anti-context-collapse discipline.
- Ops: `add` (a section), `update` (id + new body), `delete` (id).
- The assembler renders sections into the spec's memory text; free-text
  MEMORY artifacts (like the 2000-char memory in the efficiency tests) are
  joined as-is.

## Retrieval (`retrieve.py`)

Hand-rolled TF-IDF, no numpy/sklearn — the core stays stdlib-only:

- tokenizer: lowercase `[a-z0-9]+` + a minimal suffix stemmer
  (`sorting→sort`, `sorted→sort`, `rules→rule`; long words only, to avoid
  mangling short ones),
- smoothed idf, length-normalized tf,
- behind a `Retriever` Protocol — an embeddings-backed retriever can slot
  in later as an optional extra without touching callers.

## Injection: what the agent actually sees

For each task evaluation, the engine renders
`insights.render_for_context(task.prompt)` +
`reflections.render_for_context(task.prompt)` into `extra_memory`, which
`build_spec` appends **after** the playbook and **before** the POLICY cap
truncates the total to `max_memory_chars` (default 4000; see
[efficiency.md](efficiency.md)). The improver gets its own retrieval
(`_lessons_text` over "agent improvement lessons") — agent memory and
improver memory are the same stores, different queries.

Ordering consequence: under a tight policy, playbook text wins over
retrieved lessons (it is injected first). A cost-aware run that tightens
the cap is betting the playbook is load-bearing and the retrieved lessons
are not — exactly the trade-off the `policy/bound-context` operator lets
the loop explore empirically.

## Known limitations (accepted, documented)

- Reflection traces carry ids/scores, not full trajectories — memory
  content is thin (L2 in the investigation's table).
- Eval memoization keys on agent mapping, not memory-store content: a
  memo-hit parent is scored with the memory *as of its evaluation*
  (comparability vs staleness, M2).
