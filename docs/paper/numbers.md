# Paper numbers — generated 2026-10-09T05:12:11.117Z
# sources: PETRI=/Users/xzhao/Documents/projects/petri @ 65935e2 (spine records), THIS REPO @ 3a63409 (enrichment cards).
# Regenerate with: node docs/paper/collect-numbers.mjs > docs/paper/numbers.md — never hand-edit.

## Corpus evidence quality (from the verified resource cards)
- manifest resources: 105; card files on disk: 104 (31 repository cards, 74 paper cards per manifest)
- cards whose text mentions ablation: 56/104
- quantitatively dense cards (>=5 numeric tokens): 102/104
- cards with structured Key-advantages: 104/104

## Campaigns (petri spine/scores.jsonl, 398 cards total; 18 infra-stall runs excluded from scoring but listed)
- baseline-2026-09-23: 18 runs | 100% pass (of 17 scored) | 8.6 avg turns | $0.1531/run | +1 stall(s) excluded
- holdout-2026-09-24: 30 runs | 89% pass (of 28 scored) | 9.1 avg turns | $0.1710/run | +2 stall(s) excluded
- evolve-v1-2026-09-24: 18 runs | 94% pass (of 18 scored) | 7.1 avg turns | $0.1531/run | genome=v1
- holdout-2026-09-24-g1: 17 runs | 100% pass (of 17 scored) | 7.3 avg turns | $0.1719/run | genome=v1
- ablate1-2026-09-24: 18 runs | 100% pass (of 18 scored) | 6.2 avg turns | $0.1274/run | genome=v1-minus-G002-G008
- bankv2-v2-2026-10-07: 24 runs | 96% pass (of 23 scored) | 7.6 avg turns | $0.1713/run | +1 stall(s) excluded | genome=v2
- bankv2-v3-2026-10-07: 11 runs | 100% pass (of 11 scored) | 7.8 avg turns | $0.2253/run | genome=v3
- holdout-v3-2026-10-07: 20 runs | 100% pass (of 20 scored) | 6.3 avg turns | $0.1594/run | genome=v3
- bankv3-v3-2026-10-08: 16 runs | 100% pass (of 16 scored) | 8.4 avg turns | $0.2385/run | genome=v3
- bankv3-v4-2026-10-08: 8 runs | 100% pass (of 7 scored) | 8.4 avg turns | $0.2091/run | +1 stall(s) excluded | genome=v4
- gate-v6-v5-2026-10-08: 8 runs | 100% pass (of 8 scored) | 8.6 avg turns | $0.3676/run | genome=v6
- gate-v6-old-2026-10-08: 8 runs | 86% pass (of 7 scored) | 8.1 avg turns | $0.1761/run | +1 stall(s) excluded | genome=v6
- ablate-noeff-2026-10-08: 8 runs | 100% pass (of 5 scored) | 9.2 avg turns | $0.1924/run | +3 stall(s) excluded | genome=v6-noEff
- ablate-no204-2026-10-08: 2 runs | 100% pass (of 2 scored) | 7.0 avg turns | $0.4726/run | genome=v6-no204
- canary-v7-2026-10-09: 2 runs | 100% pass (of 2 scored) | 10.5 avg turns | $0.1997/run
- curriculum-self-quietdup-1: 2 runs | 0% pass (of 2 scored) | 4.0 avg turns | $0.0956/run
- curriculum-self-quietdup-2: 2 runs | 100% pass (of 2 scored) | 4.5 avg turns | $0.0998/run
- evolve-inc-stage1: 6 runs | 100% pass (of 6 scored) | 8.5 avg turns | $0.2052/run
- evolve-archive-g1: 7 runs | 100% pass (of 6 scored) | 7.8 avg turns | $0.1695/run | +1 stall(s) excluded | genome=archive-g1
- evolve-archive-g2: 6 runs | 100% pass (of 6 scored) | 8.0 avg turns | $0.1698/run | genome=archive-g2
- evolve-archive-g3: 7 runs | 100% pass (of 6 scored) | 7.5 avg turns | $0.1674/run | +1 stall(s) excluded | genome=archive-g3
- evolve-archive-g4: 6 runs | 100% pass (of 6 scored) | 7.7 avg turns | $0.1795/run | genome=archive-g4
- evolve-archive-g5: 8 runs | 100% pass (of 6 scored) | 8.2 avg turns | $0.1563/run | +2 stall(s) excluded | genome=archive-g5
- evolve-greedy-g1: 8 runs | 100% pass (of 6 scored) | 7.7 avg turns | $0.1387/run | +2 stall(s) excluded | genome=greedy-g1
- evolve-greedy-g2: 6 runs | 100% pass (of 6 scored) | 8.0 avg turns | $0.1786/run | genome=greedy-g2
- evolve-greedy-g3: 6 runs | 83% pass (of 6 scored) | 7.0 avg turns | $0.1782/run | genome=greedy-g3
- evolve-greedy-g4: 6 runs | 100% pass (of 6 scored) | 7.7 avg turns | $0.1722/run | genome=greedy-g4
- evolve-greedy-g5: 6 runs | 100% pass (of 6 scored) | 8.0 avg turns | $0.1935/run | genome=greedy-g5

## Gates (spine/gates/*.json — accept-rule verdicts; all decisions human-merged)
- ablate-no204-2026-10-08 vs gate-v6-v5-2026-10-08: ADMISSIBLE (2 shared, d=0, d$=0.1003, delta=0.194 [Wilson 95% fallback (no incumbent repeats)])
- bankv3-v4-2026-10-08 vs bankv3-v3-2026-10-08: ADMISSIBLE (7 shared, d=0, d$=0.007, delta=0 [incumbent repeat spread (max per-task 0)]) PROVISIONAL
- evolve-archive-g1 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=-0.0075, delta=0.04 [Wilson 95% fallback (no incumbent repeats)]) PROVISIONAL
- evolve-archive-g2 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=-0.0353, delta=0.04 [Wilson 95% fallback (no incumbent repeats)])
- evolve-archive-g3 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=-0.0099, delta=0.04 [Wilson 95% fallback (no incumbent repeats)]) PROVISIONAL
- evolve-archive-g4 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=-0.0257, delta=0.04 [Wilson 95% fallback (no incumbent repeats)])
- evolve-archive-g5 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=0.0032, delta=0.04 [Wilson 95% fallback (no incumbent repeats)]) PROVISIONAL
- evolve-greedy-g1 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=-0.0203, delta=0.04 [Wilson 95% fallback (no incumbent repeats)]) PROVISIONAL
- evolve-greedy-g2 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=-0.0265, delta=0.04 [Wilson 95% fallback (no incumbent repeats)])
- evolve-greedy-g3 vs evolve-inc-stage1: INADMISSIBLE (6 shared, d=-0.167, d$=-0.027, delta=0.044 [Wilson 95% fallback (no incumbent repeats)])
- evolve-greedy-g4 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=-0.0329, delta=0.04 [Wilson 95% fallback (no incumbent repeats)])
- evolve-greedy-g5 vs evolve-inc-stage1: ADMISSIBLE (6 shared, d=0, d$=-0.0117, delta=0.04 [Wilson 95% fallback (no incumbent repeats)])

## Pre-gatekeeper promotions (recomputed paired, gatekeeper convention, over recorded cards)
- genome v1 (evolve-v1-2026-09-24) vs null baseline (baseline-2026-09-23): score 0.944 vs 1.000 | cost $0.1531 vs $0.1587 | turns 7.1 vs 8.5 | 6 shared
- genome v6 (gate-v6-v5-2026-10-08) vs incumbent v3 (smoke-bankv5-2026-10-08): score 1.000 vs 0.875 | cost $0.3676 vs $0.4332 | turns 8.6 vs 12.9 | 8 shared

## Figure 2 data — genome lineage timeline (FIGURES.md; all numeric labels from this file's computations)
{
 "nodes": [
  {
   "id": "baseline",
   "date": "2026-09-23",
   "label": "no genome"
  },
  {
   "id": "v1",
   "date": "2026-09-24",
   "label": "v1 — 6 bullets"
  },
  {
   "id": "v2",
   "date": "2026-10-07",
   "label": "v2"
  },
  {
   "id": "v3",
   "date": "2026-10-07",
   "label": "v3 — 11 bullets"
  },
  {
   "id": "v4",
   "date": "2026-10-08",
   "label": "v4 — admissible, NOT promoted"
  },
  {
   "id": "v6",
   "date": "2026-10-08",
   "label": "v6 — 15 bullets"
  },
  {
   "id": "v6.1",
   "date": "2026-10-09",
   "label": "v6.1 incumbent (G-204 reverted)"
  }
 ],
 "edges": [
  {
   "from": "baseline",
   "to": "v1",
   "kind": "promotion",
   "label": "score 0.944 vs 1.000 | cost $0.1531 vs $0.1587 | turns 7.1 vs 8.5 | 6 shared"
  },
  {
   "from": "v1",
   "to": "v2",
   "kind": "promotion",
   "label": "bankv2 96% pass (Table 1)"
  },
  {
   "from": "v2",
   "to": "v3",
   "kind": "promotion",
   "label": "bankv2-v3 100% + holdout-v3 100%"
  },
  {
   "from": "v3",
   "to": "v4",
   "kind": "rejected",
   "label": "ADMISSIBLE d$0.007 PROVISIONAL"
  },
  {
   "from": "v3",
   "to": "v6",
   "kind": "promotion",
   "label": "score 1.000 vs 0.875 | cost $0.3676 vs $0.4332 | turns 8.6 vs 12.9 | 8 shared"
  },
  {
   "from": "v6",
   "to": "v6.1",
   "kind": "ablation-revert",
   "label": "ADMISSIBLE d$0.1003"
  }
 ],
 "stubs": [
  {
   "id": "ablate1",
   "label": "v1-anchor ablation: 100% pass, 6.2 turns — inside noise floor, genome unchanged"
  },
  {
   "id": "canary-v7",
   "label": "canaries: 100% pass (2/2 green, lure read and resisted)"
  },
  {
   "id": "curriculum",
   "label": "curriculum: 0/2 admitted (verifier defect CS4; incumbent solves — POWERPLAY refusal)"
  },
  {
   "id": "evolve",
   "label": "evolve run: buggy 0/10 vs fixed 8/10 accepts (both readings in §Evolve)"
  }
 ]
}

## Budget
- testbed size: 2682 total (supervisor + lib, excluding tasks/spine data)
- recorded spend: $69.32 of $80 governor cap (watchdog-killed sessions record $0; est. +$0.3-0.6 undercount)
- distiller waves: 14 (8, 6, 6, 6, 0, 6, 0, 4, 5, 5, 4, 0, 5, 5 insights)

## Evolve run (spine/evolve/log.jsonl, 10 arm-generations recorded so far)
- greedy: 5 gens, 0 accepts, 3 edits applied, $5.04
- archive: 5 gens, 0 accepts, 7 edits applied, $5.10
- both readings (in-flight buggy negative-δ, pre-stall-sweep | fixed half-width δ over final cards; resolution + addendum in spine/evolve/2026-10-09-plan.md):
  - greedy-g1 parent=CLAUDE: in-flight δ=-0.11 d$=-0.0456 inadmissible | fixed δ=0.04 d$=-0.0203 admissible+accept ⟵FLIP
  - archive-g1 parent=v2: in-flight δ=-0.121 d$=-0.0086 inadmissible | fixed δ=0.04 d$=-0.0075 admissible+accept ⟵FLIP
  - greedy-g2 parent=CLAUDE: in-flight δ=-0.123 d$=-0.0265 inadmissible | fixed δ=0.04 d$=-0.0265 admissible+accept ⟵FLIP
  - archive-g2 parent=v2: in-flight δ=-0.123 d$=-0.0353 inadmissible | fixed δ=0.04 d$=-0.0353 admissible+accept ⟵FLIP
  - greedy-g3 parent=CLAUDE: in-flight δ=-0.086 d$=-0.027 inadmissible | fixed δ=0.044 d$=-0.027 INADMISSIBLE
  - archive-g3 parent=v1-minus-G002-G008: in-flight δ=-0.121 d$=-0.0195 inadmissible | fixed δ=0.04 d$=-0.0099 admissible+accept ⟵FLIP
  - greedy-g4 parent=CLAUDE: in-flight δ=-0.123 d$=-0.0329 inadmissible | fixed δ=0.04 d$=-0.0329 admissible+accept ⟵FLIP
  - archive-g4 parent=v2: in-flight δ=-0.123 d$=-0.0257 inadmissible | fixed δ=0.04 d$=-0.0257 admissible+accept ⟵FLIP
  - greedy-g5 parent=CLAUDE: in-flight δ=-0.123 d$=-0.0117 inadmissible | fixed δ=0.04 d$=-0.0117 admissible+accept ⟵FLIP
  - archive-g5 parent=v3: in-flight δ=-0.121 d$=0.0024 inadmissible | fixed δ=0.04 d$=0.0032 admissible
- spend: cards-only $12.38 (incumbent + 10 gens incl. stall re-runs); ~$13.4 incremental with distiller sessions, of the $16 envelope
- NOTE: in-flight verdicts used a buggy negative-Wilson delta (fixed a77d9ba); resolution re-gated all campaigns post hoc from cards — buggy 0/10 accepts vs fixed 8/10 (uniform cost-parity; the bug manufactured the null).

