# Writing progress tracker (composer discipline)

| Section | Status | Quality gate (5-dim, /20) |
|---|---|---|
| Abstract | final for draft; revisit at author-kit conversion | 19 (re-check after all sections) |
| §1 Introduction + contributions | final | 19 |
| §2 Related work | final | 19 (citation 3/4 until author fields fill) |
| §3 Testbed (3.1–3.8) | final | 19 |
| §4 CS1–CS7 catalog | final | 19 |
| §5 Results (5.1–5.4) | final (evolve resolved; both readings) | 19 |
| §6 Threats | final | 18 |
| §7 Discussion | final | 19 |
| §8 Conclusion | final | 19 |
| References (23, corpus-verified) | titles+urls verified vs manifest; **authors to fill from arXiv pages at author-kit conversion** | — |
| App A/B/C | final | 18 |

Cross-chapter coherence: run 2026-10-09 — no placeholders remain; "append-only" usage uniform;
45-campaign count matches records; numbers cross-checked against numbers.md (2682 LOC → "~2,700";
$74 lifetime; 18/398 stalls; 12 gates; both-readings table).

## Remaining to submission (see VENUES.md timeline)

- [x] F1 source written (`fig1-loop.mmd`, mermaid; render at author-kit time)
- [x] F2 data emitted (numbers.md "Figure 2 data" block; render at author-kit time)
- [x] F3 data (both-readings table) in numbers.md
- [x] Author fields for all 23 references (verified: 22 via arXiv API, FunSearch via Nature dc.creator)
- [x] Render F1/F2 as art (`figures/fig1-loop.png` 1904×440, `figures/fig2-lineage.png` 1400×224 via
      mermaid.ink; F2 generated from numbers.md by `fig2-render.mjs` — no hand-typed numbers; both
      visually verified; re-render if the kit needs different sizes) — commit f006578
- [x] Anonymization pass (2026-10-09): no author identity, no own-repo URLs (only third-party
      github.com/jennyzzt/dgm citation), "this repo" → "the study repository"; HTML comments to strip
      at LaTeX conversion (they name the companion repo/commit — fine in source, gone in PDF)
- [x] Phase-5 final pass (2026-10-09): abstract re-enumerated to match CS1–CS7 one-to-one (was 7 items
      that split CS2 and omitted CS6); "[survey pointer]" placeholder resolved to §2+App A pointer;
      7-dimension re-score with figures+authors done: argument 8, literature 8, clarity 8, originality 9,
      rigor 9, structure 8, platform 7 (markdown→AAAI kit pending) = **57/70 ≥ 56 threshold**; the sole
      below-8 dimension is the known LaTeX conversion step
- [ ] AAAI-27 author kit (LaTeX) conversion — target Nov 6
- [ ] Final read-aloud pass + abstract re-check; submit by Nov 20 AoE
