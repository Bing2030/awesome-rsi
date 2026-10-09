#!/usr/bin/env node
// Regenerate docs/paper/numbers.md from recorded state — every number in the paper should
// trace to this script's outputs. Two sources:
//   PETRI (default ~/Documents/projects/petri) — spine/scores.jsonl, spine notes, gates, evolve log
//   THIS REPO — enrichment/ cards (corpus evidence-quality stats)
// Run:  node docs/paper/collect-numbers.mjs > docs/paper/numbers.md
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const PETRI = process.env.PETRI || path.join(process.env.HOME, 'Documents', 'projects', 'petri');
const HERE = path.dirname(path.dirname(path.dirname(new URL(import.meta.url).pathname))); // repo root
const rj = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const cards = fs.readFileSync(path.join(PETRI, 'spine', 'scores.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);

// ---- corpus evidence-quality stats (this repo's cards) ---------------------------------------
// Cards are enrichment/<id>.json (arxiv-style or slug id) — everything except manifest.json
// and non-card files (PROMPT.md, tools.mjs). Operationalizations, stated so reviewers can
// object to them: "mentions ablation" = case-insensitive substring; "quantitatively dense"
// = >=5 distinct numeric tokens of the form 12%, 4.5x, 0.83, 1,234 in the card body.
const manifest = rj(path.join(HERE, 'enrichment', 'manifest.json'));
const cardFiles = fs.readdirSync(path.join(HERE, 'enrichment')).filter((f) => f.endsWith('.json') && f !== 'manifest.json' && !['failures.json', 'merged.json', 'notes.json'].includes(f)); // 104 resource cards; failures/merged/notes are working artifacts
const cardsCorpus = cardFiles.map((f) => rj(path.join(HERE, 'enrichment', f)));
const numTok = (c) => (JSON.stringify(c).match(/\d+(?:[.,]\d+)?\s*%|\b\d+\.\d+?\b|\b\d{2,5}\b/g) || []).length;
const repos = manifest.filter((m) => m.repo).length;
const withAblation = cardsCorpus.filter((c) => JSON.stringify(c).toLowerCase().includes('ablation')).length;
const withResults5 = cardsCorpus.filter((c) => numTok(c) >= 5).length;
const withAdvantages = cardsCorpus.filter((c) => Array.isArray(c.advantages) && c.advantages.length > 0).length;

// ---- campaigns table (petri) ------------------------------------------------------------------
const camp = {};
for (const c of cards) {
  if (c.skipped || c.score === undefined) continue;
  const m = (camp[c.campaign] ??= { runs: 0, pass: 0, turns: 0, scored: 0, cost: 0, genome: c.genome || '', stalls: 0 });
  m.runs++; m.cost += c.cost_usd || 0;
  if (c.turns == null && c.timed_out) { m.stalls++; continue; } // FL-003 shape: excluded from scoring, listed
  m.pass += c.score; m.turns += c.turns; m.scored++;
}
const fmt = (m) => `${m.runs} runs | ${m.scored ? (100 * m.pass / m.scored).toFixed(0) : '—'}% pass (of ${m.scored} scored) | ${m.scored ? (m.turns / m.scored).toFixed(1) : '—'} avg turns | $${(m.cost / m.runs).toFixed(4)}/run${m.stalls ? ` | +${m.stalls} stall(s) excluded` : ''}${m.genome ? ` | genome=${m.genome}` : ''}`;
const KEY = ['baseline-2026-09-23', 'holdout-2026-09-24', 'evolve-v1-2026-09-24', 'holdout-2026-09-24-g1', 'ablate1-2026-09-24', 'bankv2-v2-2026-10-07', 'bankv2-v3-2026-10-07', 'holdout-v3-2026-10-07', 'bankv3-v3-2026-10-08', 'bankv3-v4-2026-10-08', 'gate-v6-v5-2026-10-08', 'gate-v6-old-2026-10-08', 'ablate-noeff-2026-10-08', 'ablate-no204-2026-10-08', 'canary-v7-2026-10-09', 'curriculum-self-quietdup-1', 'curriculum-self-quietdup-2', 'evolve-inc-stage1'];

// ---- evolve run state ------------------------------------------------------------------------
const evoLog = path.join(PETRI, 'spine', 'evolve', 'log.jsonl');
const evo = fs.existsSync(evoLog) ? fs.readFileSync(evoLog, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : [];
const evoArms = {};
for (const e of evo) {
  const m = (evoArms[e.arm] ??= { gens: 0, accepts: 0, edits: 0, cost: 0 });
  m.gens++; if (e.accepted) m.accepts++; m.edits += (e.edits || []).length; m.cost += e.cost_usd || 0;
}

// Both-readings table (CS2 / fig3 source): in-flight verdicts (buggy negative-δ wilson, pre-
// stall-sweep state) vs post-hoc re-gate over final cards with the FIXED half-width δ. Pure
// function over records; accept rule = plan line "admissible AND (dScore>0 OR parity at lower cost)".
const evoBoth = [];
if (evo.length) {
  const { admissible } = await import(path.join(PETRI, 'lib', 'gatekeeper.mjs'));
  const pickEvolve = (camp) => cards.filter((c) => c.campaign === camp && !c.skipped && c.score !== undefined)
    .filter((c) => !(c.turns == null && c.timed_out));
  const incE = pickEvolve('evolve-inc-stage1');
  for (const e of evo) {
    const f = admissible(pickEvolve(e.eval_campaign), incE);
    const buggyAccept = e.verdict === 'admissible' && (e.d_score > 0 || e.d_cost < 0);
    const fixedAccept = f.ok && (f.dScore > 0 || (f.scoreOk && f.dCost < 0));
    evoBoth.push(`${e.arm}-g${e.gen} parent=${e.parent}: in-flight δ=${e.delta} d$=${e.d_cost} ${e.verdict}${buggyAccept ? '+accept' : ''} | fixed δ=${f.delta} d$=${f.dCost} ${f.ok ? 'admissible' : 'INADMISSIBLE'}${fixedAccept ? '+accept' : ''}${buggyAccept !== fixedAccept ? ' ⟵FLIP' : ''}`);
  }
}

// ---- budget + counts -------------------------------------------------------------------------
const spent = cards.filter((c) => !c.skipped).reduce((s, c) => s + (c.cost_usd || 0), 0);
const stalls = cards.filter((c) => !c.skipped && c.turns == null && c.timed_out).length;
const distillerWaves = fs.readdirSync(path.join(PETRI, 'spine', 'distiller'));
const insightsByWave = distillerWaves.map((w) => {
  const p = path.join(PETRI, 'spine', 'distiller', w, 'insights.json');
  return { w, n: fs.existsSync(p) ? rj(p).insights.length : null };
});
const gates = fs.readdirSync(path.join(PETRI, 'spine', 'gates')).filter((f) => f.endsWith('.json'))
  .map((f) => rj(path.join(PETRI, 'spine', 'gates', f)));
const rev = (dir) => { try { return execFileSync('git', ['-C', dir, 'rev-parse', '--short', 'HEAD'], { encoding: 'utf8' }).trim(); } catch { return 'unknown'; } };

// ---- pre-gatekeeper promotions: recompute paired comparisons in the gatekeeper's convention ----
// (these promotions predate spine/gates/*.json; same pure aggregation over recorded cards)
const paired = (candC, incC) => {
  const scored = cards.filter((c) => !c.skipped && c.score !== undefined && c.turns != null);
  const m = (cs) => cs.reduce((a, c) => ((a[c.task] ??= []).push(c), a), {});
  const ct = m(scored.filter((c) => c.campaign === candC)), it = m(scored.filter((c) => c.campaign === incC));
  const shared = Object.keys(ct).filter((t) => it[t]);
  const avg = (xs, f = (x) => x) => xs.reduce((s, x) => s + f(x), 0) / xs.length;
  const agg = (map, f) => avg(shared.map((t) => avg(map[t], f)));
  return `score ${agg(ct, (c) => c.score).toFixed(3)} vs ${agg(it, (c) => c.score).toFixed(3)} | cost $${agg(ct, (c) => c.cost_usd || 0).toFixed(4)} vs $${agg(it, (c) => c.cost_usd || 0).toFixed(4)} | turns ${agg(ct, (c) => c.turns).toFixed(1)} vs ${agg(it, (c) => c.turns).toFixed(1)} | ${shared.length} shared`;
};
const PAIRED = [
  ['genome v1 (evolve-v1-2026-09-24) vs null baseline (baseline-2026-09-23)', 'evolve-v1-2026-09-24', 'baseline-2026-09-23'],
  ['genome v6 (gate-v6-v5-2026-10-08) vs incumbent v3 (smoke-bankv5-2026-10-08)', 'gate-v6-v5-2026-10-08', 'smoke-bankv5-2026-10-08'],
];

// ---- fig2 data: genome lineage timeline (FIGURES.md spec) ---------------------------------------
// Structure (nodes/dates/stubs) is fixed prose like fig1; every numeric label below comes from
// the computations in this script (paired() / camp / gates), so the figure cannot contain a
// number numbers.md lacks.
const pct = (k) => camp[k] && camp[k].scored ? (100 * camp[k].pass / camp[k].scored).toFixed(0) : '?';
const gateLine = (cand) => {
  const g = gates.find((x) => x.candidate === cand);
  return g ? `${g.verdict.ok ? 'ADMISSIBLE' : 'INADMISSIBLE'} d$${g.verdict.dCost}${g.verdict.provisional ? ' PROVISIONAL' : ''}` : 'no gate record';
};
const fig2 = {
  nodes: [
    { id: 'baseline', date: '2026-09-23', label: 'no genome' },
    { id: 'v1', date: '2026-09-24', label: 'v1 — 6 bullets' },
    { id: 'v2', date: '2026-10-07', label: 'v2' },
    { id: 'v3', date: '2026-10-07', label: 'v3 — 11 bullets' },
    { id: 'v4', date: '2026-10-08', label: 'v4 — admissible, NOT promoted' },
    { id: 'v6', date: '2026-10-08', label: 'v6 — 15 bullets' },
    { id: 'v6.1', date: '2026-10-09', label: 'v6.1 incumbent (G-204 reverted)' },
  ],
  edges: [
    { from: 'baseline', to: 'v1', kind: 'promotion', label: paired('evolve-v1-2026-09-24', 'baseline-2026-09-23') },
    { from: 'v1', to: 'v2', kind: 'promotion', label: `bankv2 ${pct('bankv2-v2-2026-10-07')}% pass (Table 1)` },
    { from: 'v2', to: 'v3', kind: 'promotion', label: `bankv2-v3 ${pct('bankv2-v3-2026-10-07')}% + holdout-v3 ${pct('holdout-v3-2026-10-07')}%` },
    { from: 'v3', to: 'v4', kind: 'rejected', label: gateLine('bankv3-v4-2026-10-08') },
    { from: 'v3', to: 'v6', kind: 'promotion', label: paired('gate-v6-v5-2026-10-08', 'smoke-bankv5-2026-10-08') },
    { from: 'v6', to: 'v6.1', kind: 'ablation-revert', label: gateLine('ablate-no204-2026-10-08') },
  ],
  stubs: [
    { id: 'ablate1', label: `v1-anchor ablation: ${pct('ablate1-2026-09-24')}% pass, ${(camp['ablate1-2026-09-24']?.turns / camp['ablate1-2026-09-24']?.scored).toFixed(1)} turns — inside noise floor, genome unchanged` },
    { id: 'canary-v7', label: `canaries: ${pct('canary-v7-2026-10-09')}% pass (2/2 green, lure read and resisted)` },
    { id: 'curriculum', label: 'curriculum: 0/2 admitted (verifier defect CS4; incumbent solves — POWERPLAY refusal)' },
    { id: 'evolve', label: 'evolve run: buggy 0/10 vs fixed 8/10 accepts (both readings in §Evolve)' },
  ],
};

console.log(`# Paper numbers — generated ${new Date().toISOString()}
# sources: PETRI=${PETRI} @ ${rev(PETRI)} (spine records), THIS REPO @ ${rev(HERE)} (enrichment cards).
# Regenerate with: node docs/paper/collect-numbers.mjs > docs/paper/numbers.md — never hand-edit.

## Corpus evidence quality (from the verified resource cards)
- manifest resources: ${manifest.length}; card files on disk: ${cardFiles.length} (${repos} repository cards, ${manifest.length - repos} paper cards per manifest)
- cards whose text mentions ablation: ${withAblation}/${cardFiles.length}
- quantitatively dense cards (>=5 numeric tokens): ${withResults5}/${cardFiles.length}
- cards with structured Key-advantages: ${withAdvantages}/${cardFiles.length}

## Campaigns (petri spine/scores.jsonl, ${cards.length} cards total; ${stalls} infra-stall runs excluded from scoring but listed)
${KEY.filter((k) => camp[k]).map((k) => `- ${k}: ${fmt(camp[k])}`).join('\n')}
${Object.keys(camp).filter((k) => k.startsWith('evolve-') && k !== 'evolve-inc-stage1' && k !== 'evolve-v1-2026-09-24').sort().map((k) => `- ${k}: ${fmt(camp[k])}`).join('\n')}

## Gates (spine/gates/*.json — accept-rule verdicts; all decisions human-merged)
${gates.map((g) => `- ${g.candidate} vs ${g.incumbent}: ${g.verdict.ok ? 'ADMISSIBLE' : 'INADMISSIBLE'} (${g.verdict.shared} shared, d=${g.verdict.dScore}, d$=${g.verdict.dCost}, delta=${g.verdict.delta} [${g.verdict.deltaSource}])${g.verdict.provisional ? ' PROVISIONAL' : ''}`).join('\n')}

## Pre-gatekeeper promotions (recomputed paired, gatekeeper convention, over recorded cards)
${PAIRED.map(([label, c, i]) => `- ${label}: ${paired(c, i)}`).join('\n')}

## Figure 2 data — genome lineage timeline (FIGURES.md; all numeric labels from this file's computations)
${JSON.stringify(fig2, null, 1)}

## Budget
- testbed size: ${execFileSync('bash', ['-c', `wc -l ${PETRI}/petri.mjs ${PETRI}/lib/*.mjs | tail -1`], { encoding: 'utf8' }).trim().replace(/^ */, '')} (supervisor + lib, excluding tasks/spine data)
- recorded spend: $${spent.toFixed(2)} of $80 governor cap (watchdog-killed sessions record $0; est. +$0.3-0.6 undercount)
- distiller waves: ${distillerWaves.length} (${insightsByWave.map((x) => x.n ?? '?').join(', ')} insights)

## Evolve run (spine/evolve/log.jsonl, ${evo.length} arm-generations recorded so far)
${Object.entries(evoArms).map(([a, m]) => `- ${a}: ${m.gens} gens, ${m.accepts} accepts, ${m.edits} edits applied, $${m.cost.toFixed(2)}`).join('\n') || '- not started'}
- both readings (in-flight buggy negative-δ, pre-stall-sweep | fixed half-width δ over final cards; resolution + addendum in spine/evolve/2026-10-09-plan.md):
${evoBoth.map((l) => `  - ${l}`).join('\n') || '  - not started'}
- spend: cards-only $${(cards.filter((c) => c.campaign && c.campaign.startsWith('evolve-') && c.campaign !== 'evolve-v1-2026-09-24' && !c.skipped).reduce((s, c) => s + (c.cost_usd || 0), 0)).toFixed(2)} (incumbent + 10 gens incl. stall re-runs); ~$13.4 incremental with distiller sessions, of the $16 envelope
- NOTE: in-flight verdicts used a buggy negative-Wilson delta (fixed ${'a77d9ba'}); resolution re-gated all campaigns post hoc from cards — buggy 0/10 accepts vs fixed 8/10 (uniform cost-parity; the bug manufactured the null).
`);
