# Enrichment subagent contract

One background subagent session per resource receives the template below with the placeholders
filled (resource metadata + its current card). Completed cards land in `enrichment/<slug>.json`;
the orchestrator validates + merges them (`node enrichment/tools.mjs merge`).

## Shared rules

- Read the actual source.
  - Papers: the local PDF under `resources/<slug>.pdf` (download first if missing:
    `curl -sL https://arxiv.org/pdf/<id> -o resources/<slug>.pdf`), extract with
    `pdftotext resources/<slug>.pdf <tmp>.txt`, and read abstract / intro / method /
    experiments / limitations — enough to name the actual mechanism and cite real numbers.
  - Repos: README (`curl https://raw.githubusercontent.com/<owner>/<repo>/main/README.md`,
    fall back to `master`, or `gh api repos/<owner>/<repo>/readme`), the file tree
    (`gh api "repos/<owner>/<repo>/git/trees/HEAD?recursive=1"`), and 2–4 key source files.
- Verify every number against the text. If a number is not in the source, it does not go in the card.
- Never invent content. If the source can't be fetched after one retry, build the best card you can
  from the abstract/README alone and say so in `_source_note`.
- Write only `enrichment/<slug>.json` (plus the PDF, if you downloaded one). Touch nothing else,
  don't run `site/generate.mjs`, don't git commit.
- Validate your JSON parses before finishing:
  `node -e 'JSON.parse(require("fs").readFileSync("<abs path>","utf8"))'`.

## Paper card schema (`enrichment/<slug>.json`)

```json
{
  "tldr": "≤45 words — the one-sentence claim",
  "method": "80–150 words — mechanically how it works: inputs, loop, gates, what evolves/trains",
  "results": ["3–5 bullets with real numbers: benchmark, metric, before→after, baselines"],
  "advantages": ["2–4 bullets — what it genuinely establishes or does better than prior work"],
  "limitations": ["2–4 bullets, from the paper's own account where possible"],
  "fits": "≤60 words — where it sits in the study arc (stages 1–10) and what it pairs with",
  "reading": "≤40 words — which sections to read",
  "_source_note": "what you actually read + confidence"
}
```

## Repo card schema

```json
{
  "what": "≤45 words",
  "architecture": ["3–4 bullets verified from README/source"],
  "advantages": ["2–3 bullets — what this substrate is uniquely good for"],
  "run": "exact install/run command from the README",
  "note": "≤50 words — what to study when you open it",
  "_source_note": "..."
}
```

Depth bar: the RRSI / RSIAgent / Harness-Zero cards in `site/curated.json` — named mechanisms,
real numbers, no generic praise.
