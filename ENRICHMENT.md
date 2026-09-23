# Resource-card enrichment plan

Every resource on the study site gets its card brought to "actually read the source" depth:
a verified methodology section, real numbers, and an explicit **Key advantages** section — the
standard set by the RSIAgent / Harness-Zero / RRSI cards. This file tracks per-resource status
across sessions.

## Protocol

1. **One subagent session per resource.** It reads the paper (local PDF, or `curl` from arXiv,
   via `pdftotext`) or the repo (README + file tree + key source files via `gh api` /
   `raw.githubusercontent.com`), then writes a card to `enrichment/<slug>.json` following the
   contract in `enrichment/PROMPT.md`.
2. **Merge.** `node enrichment/tools.mjs merge` validates every card against the schema and folds
   it into `site/curated.json`; `node site/generate.mjs` rebuilds the pages. The orchestrator
   session runs both, commits per wave, and regenerates the table below
   (`node enrichment/tools.mjs table`).
3. **Status.** The table between the markers below is generated from `enrichment/manifest.json`
   plus the filesystem: `merged.json` = merged (✓), `failures.json` = failed (✗), card file
   present = awaiting merge (◐). Hand-editable per-resource notes live in `enrichment/notes.json`.

Legend: ✓ merged · ◐ card written, awaiting merge · ✗ failed · ☐ pending.
`had` = a card existed and is deepened in place · **new** = first card for this resource.
PDF column: local PDF present (`yes`/`no`/`-` for repos) — agents download missing ones.

## Priority order

Thinnest cards first (papers without an in-card Method section, then lowest card word count),
then everything else — every resource is eventually re-reviewed against its source. Study-guide
stage order breaks ties. Missing PDFs are downloaded along the way.

<!-- BEGIN STATUS TABLE -->
| # | Stage | Type | Slug | Title | Card | PDF | Status | Notes |
|---|-------|------|------|-------|------|-----|--------|-------|
| 1 | 1 | paper | 1606.04474 | Learning to Learn by Gradient Descent by Gradient Descent | had | yes | ☐ |  |
| 2 | 1 | paper | 2410.04444 | Gödel Agent: A Self-Referential Agent Framework for Recursive Self-Improvement | had | yes | ☐ |  |
| 3 | 1 | paper | 2003.03384 | AutoML-Zero: Evolving Machine Learning Algorithms From Scratch | had | yes | ☐ |  |
| 4 | 1 | paper | 1905.10985 | AI-GAs: AI-Generating Algorithms, an Alternate Paradigm for Producing General Artificial Intelligence | had | yes | ☐ |  |
| 5 | 1 | paper | frontiers-quality-diversity-2016 | Quality Diversity: A New Frontier for Evolutionary Computation | had | yes | ☐ |  |
| 6 | 1 | paper | 1504.04909 | Illuminating Search Spaces by Mapping Elites | had | yes | ☐ |  |
| 7 | 1 | paper | 1112.5309 | POWERPLAY: Training an Increasingly General Problem Solver by Continually Searching for the Simplest Still Unsolvable Problem | had | yes | ☐ |  |
| 8 | 2 | paper | 2310.03714 | DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines | had | yes | ☐ |  |
| 9 | 2 | paper | 2406.07496 | TextGrad: Automatic "Differentiation" via Text | had | yes | ☐ |  |
| 10 | 2 | paper | 2309.03409 | Large Language Models as Optimizers | had | yes | ☐ |  |
| 11 | 2 | paper | 2309.16797 | Promptbreeder: Self-Referential Self-Improvement Via Prompt Evolution | had | yes | ☐ |  |
| 12 | 2 | paper | 2310.04406 | Language Agent Tree Search Unifies Reasoning, Acting, and Planning in Language Models | had | yes | ☐ |  |
| 13 | 3 | paper | 2303.17651 | Self-Refine: Iterative Refinement with Self-Feedback | had | yes | ☐ |  |
| 14 | 3 | paper | 2309.11495 | Chain-of-Verification Reduces Hallucination in Large Language Models | had | yes | ☐ |  |
| 15 | 3 | paper | 2305.11738 | CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing | had | yes | ☐ |  |
| 16 | 3 | paper | 2203.11171 | Self-Consistency Improves Chain of Thought Reasoning in Language Models | had | yes | ☐ |  |
| 17 | 3 | paper | 2305.20050 | Let's Verify Step by Step | had | yes | ☐ |  |
| 18 | 3 | paper | 2310.01798 | Large Language Models Cannot Self-Correct Reasoning Yet | had | yes | ☐ |  |
| 19 | 4 | paper | 2303.11366 | Reflexion: Language Agents with Verbal Reinforcement Learning | had | yes | ☐ |  |
| 20 | 4 | paper | 2305.16291 | Voyager: An Open-Ended Embodied Agent with Large Language Models | had | yes | ☐ |  |
| 21 | 4 | paper | 2308.10144 | ExpeL: LLM Agents Are Experiential Learners | had | yes | ☐ |  |
| 22 | 4 | paper | 2502.12110 | A-MEM: Agentic Memory for LLM Agents | had | yes | ☐ |  |
| 23 | 4 | paper | 2305.10250 | MemoryBank: Enhancing Large Language Models with Long-Term Memory | had | yes | ✓ |  |
| 24 | 4 | paper | 2510.04618 | Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models | had | yes | ☐ |  |
| 25 | 4 | paper | 2510.16079 | EvolveR: Self-Evolving LLM Agents through an Experience-Driven Lifecycle | had | yes | ☐ |  |
| 26 | 4 | paper | 2604.15097 | From Procedural Skills to Strategy Genes: Towards Experience-Driven Test-Time Evolution | had | yes | ☐ |  |
| 27 | 4 | paper | 2602.07755 | Learning to Continually Learn via Meta-learning Agentic Memory Designs | had | yes | ☐ |  |
| 28 | 4 | paper | 2607.14159 | MemoHarness: Agent Harnesses That Learn from Experience | had | yes | ☐ |  |
| 29 | 4 | paper | 2607.26784 | SkillRise: Agentic Reinforcement Learning for Cross-Task Skill Evolution | had | yes | ☐ |  |
| 30 | 4 | paper | 2605.23904 | SkillOpt: Executive Strategy for Self-Evolving Agent Skills | had | yes | ☐ |  |
| 31 | 4 | paper | 2512.18746 | MemEvolve: Meta-Evolution of Agent Memory Systems | had | yes | ☐ |  |
| 32 | 4 | paper | 2607.05297 | MetaSkill-Evolve: Recursive Self-Improvement of LLM Agents via Two-Timescale Meta-Skill Evolution | had | yes | ☐ |  |
| 33 | 5 | paper | 2408.08435 | Automated Design of Agentic Systems | had | yes | ☐ |  |
| 34 | 5 | paper | 2310.02304 | Self-Taught Optimizer (STOP): Recursively Self-Improving Code Generation | had | yes | ☐ |  |
| 35 | 5 | paper | 2604.25850 | Agentic Harness Engineering: Observability-Driven Automatic Evolution of Coding-Agent Harnesses | had | yes | ☐ |  |
| 36 | 5 | paper | 2608.12307 | AI4AI at Test-Time: Strong-to-Weak Capability Transfer via Harnesses | had | yes | ☐ |  |
| 37 | 5 | paper | 2603.03329 | AutoHarness: Improving LLM Agents by Automatically Synthesizing a Code Harness | had | yes | ☐ |  |
| 38 | 5 | paper | 2605.09998 | Continual Harness: Online Adaptation for Self-Improving Foundation Agents | had | yes | ☐ |  |
| 39 | 5 | paper | 2608.05446 | EvoHarness-RL: Learning Self-Evolving Runtime Harness for Long-Horizon LLM Agents | had | yes | ☐ |  |
| 40 | 5 | paper | 2609.20519 | SoL-Pi: Recursively Scaling Auto-Research Loops for Efficient Agent Harness | had | yes | ☐ |  |
| 41 | 5 | paper | 2609.24974 | Harness-Zero: Harness Distillation via Agent-as-Harness | had | yes | ☐ |  |
| 42 | 5 | paper | 2609.24972 | RRSI: Regularized Recursive Self-Improvement of Agent Harnesses | had | yes | ☐ |  |
| 43 | 5 | paper | 2603.19461 | Hyperagents | had | yes | ☐ |  |
| 44 | 5 | paper | 2605.27276 | SIA: Self Improving AI with Harness & Weight Updates | had | yes | ☐ |  |
| 45 | 5 | paper | 2603.18000 | AgentFactory: A Self-Evolving Framework Through Executable Subagent Accumulation and Reuse | had | yes | ☐ |  |
| 46 | 5 | paper | 2604.20133 | EvoAgent: An Evolvable Agent Framework with Skill Learning and Multi-Agent Delegation | had | yes | ☐ |  |
| 47 | 5 | paper | 2507.03616 | EvoAgentX: An Automated Framework for Evolving Agentic Workflows | had | yes | ☐ |  |
| 48 | 5 | paper | 2510.23601 | Alita-G: Self-Evolving Generative Agent for Agent Generation | had | yes | ☐ |  |
| 49 | 5 | paper | 2402.17574 | Agent-Pro: Learning to Evolve via Policy-Level Reflection and Optimization | had | yes | ✓ |  |
| 50 | 5 | paper | 2409.00872 | Self-evolving Agents with Reflective and Memory-Augmented Abilities | had | yes | ✓ |  |
| 51 | 5 | paper | 2609.15364 | RSIAgent: Autonomous Exploration for Recursive Self-improvement in New Environments | had | yes | ☐ |  |
| 52 | 6 | paper | 2305.19118 | Encouraging Divergent Thinking in Large Language Models through Multi-Agent Debate | had | yes | ☐ |  |
| 53 | 6 | paper | 2305.14325 | Improving Factuality and Reasoning in Language Models through Multiagent Debate | had | yes | ✓ |  |
| 54 | 6 | paper | 2505.15734 | DEBATE, TRAIN, EVOLVE: Self Evolution of Language Model Reasoning | had | yes | ☐ |  |
| 55 | 6 | paper | 2511.16043 | Agent0: Unleashing Self-Evolving Agents from Zero Data via Tool-Integrated Reasoning | had | yes | ✓ |  |
| 56 | 6 | paper | 2406.14228 | EvoAgent: Towards Automatic Multi-Agent Generation via Evolutionary Algorithms | had | yes | ✓ |  |
| 57 | 6 | paper | 2403.08715 | SOTOPIA-π: Interactive Learning of Socially Intelligent Language Agents | had | yes | ✓ |  |
| 58 | 7 | paper | 2505.22954 | Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents | had | yes | ☐ |  |
| 59 | 7 | paper | 2504.15228 | A Self-Improving Coding Agent | had | yes | ☐ |  |
| 60 | 7 | paper | 2412.21139 | Training Software Engineering Agents and Verifiers with SWE-Gym | had | yes | ☐ |  |
| 61 | 7 | paper | 2304.05128 | Teaching Large Language Models to Self-Debug | had | yes | ☐ |  |
| 62 | 7 | paper | 2312.13010 | AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation | had | yes | ☐ |  |
| 63 | 8 | paper | 2408.06292 | The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery | had | yes | ☐ |  |
| 64 | 8 | paper | nature-ai-scientist-v2-2026 | Towards End-to-End Automation of AI Research (The AI Scientist-v2) | had | yes | ☐ |  |
| 65 | 8 | paper | 2601.14525 | Towards Execution-Grounded Automated AI Research | had | yes | ☐ |  |
| 66 | 8 | paper | 2608.17906 | AutoResearch: Insight In, Hallucination Out | had | yes | ☐ |  |
| 67 | 8 | paper | 2607.28568 | Frontis-MA1: Training an AI4AI Model towards Recursive Self-Improvement in Machine Learning Engineering | had | yes | ☐ |  |
| 68 | 8 | paper | 2603.01712 | FT-Dojo: Towards Autonomous LLM Fine-Tuning with Language Agents | had | yes | ☐ |  |
| 69 | 8 | paper | 2606.06473 | MLEvolve: A Self-Evolving Framework for Automated Machine Learning Algorithm Discovery | had | yes | ✓ |  |
| 70 | 9 | paper | nature-funsearch-2024 | Mathematical Discoveries from Program Search with Large Language Models | had | yes | ☐ |  |
| 71 | 9 | paper | 2506.13131 | AlphaEvolve: A Coding Agent for Scientific and Algorithmic Discovery | had | yes | ☐ |  |
| 72 | 9 | paper | 2601.10657 | PACEvolve: Enabling Long-Horizon Progress-Aware Consistent Evolution | had | yes | ✓ |  |
| 73 | 9 | paper | openreview-higher-order-evolution-2024 | Higher Order and Self-Referential Evolution for Population-based Methods | had | no | ✗ | PDF challenge-blocked — not enriched this pass; see failures.json |
| 74 | 9 | paper | 1901.01753 | Paired Open-Ended Trailblazer (POET): Endlessly Generating Increasingly Complex and Diverse Learning Environments and Their Solutions | had | yes | ☐ |  |
| 75 | 10 | repo | agent-zero | Agent Zero | had | - | ☐ |  |
| 76 | 10 | repo | deepseek-harness | DeepSeek Harness | had | - | ☐ |  |
| 77 | 10 | repo | openclaw | OpenClaw | had | - | ☐ |  |
| 78 | 10 | repo | pi | Pi | had | - | ☐ |  |
| 79 | 10 | repo | agentfactory | AgentFactory (code) | had | - | ✓ |  |
| 80 | 10 | repo | dgm | Darwin Gödel Machine (code) | had | - | ✓ |  |
| 81 | 10 | repo | godel-agent | Gödel Agent (code) | had | - | ✓ |  |
| 82 | 10 | repo | hermes-agent | Hermes Agent | had | - | ☐ |  |
| 83 | 10 | repo | hyperagents | HyperAgents (code) | had | - | ✓ |  |
| 84 | 10 | repo | seal | SEAL | had | - | ☐ |  |
| 85 | 10 | repo | sia | SIA (code) | had | - | ✓ |  |
| 86 | 10 | repo | ace | ACE (code) | had | - | ✓ |  |
| 87 | 10 | repo | alma | ALMA (code) | had | - | ✓ |  |
| 88 | 10 | repo | continual-harness | Continual Harness (code) | had | - | ✓ |  |
| 89 | 10 | repo | evoagentx | EvoAgentX (code) | had | - | ✓ |  |
| 90 | 10 | repo | evolver | EvolveR (code) | had | - | ✓ |  |
| 91 | 10 | repo | letta-code | Letta Code | had | - | ☐ |  |
| 92 | 10 | repo | memento-skills | Memento-Skills | had | - | ✓ |  |
| 93 | 10 | repo | reef | Reef | had | - | ✓ |  |
| 94 | 10 | repo | voyager | Voyager (code) | had | - | ✓ |  |
| 95 | 10 | repo | rsiagent | RSIAgent (code) | had | - | ☐ |  |
| 96 | 10 | repo | harness-zero | Harness-Zero (code) | had | - | ☐ |  |
| 97 | 10 | repo | rrsi | RRSI (code) | had | - | ☐ |  |
| 98 | 10 | repo | adas | ADAS (code) | had | - | ✓ |  |
| 99 | 10 | repo | ai-scientist | AI Scientist (code) | had | - | ☐ |  |
| 100 | 10 | repo | autoresearch | autoresearch | had | - | ☐ |  |
| 101 | 10 | repo | evolutionary-model-merge | Evolutionary Model Merge | had | - | ☐ |  |
| 102 | 10 | repo | funsearch | FunSearch (code) | had | - | ☐ |  |
| 103 | 10 | repo | mlevolve | MLEvolve (code) | had | - | ✓ |  |
| 104 | 10 | repo | openevolve | OpenEvolve | had | - | ☐ |  |
| 105 | 10 | repo | poet | POET (code) | had | - | ✓ |  |
<!-- END STATUS TABLE -->

## Progress log

- 2026-09-23 — Plan created; `Key advantages` card field + rendering landed in the site
  generator; wave 1 launched (8 subagent sessions).
