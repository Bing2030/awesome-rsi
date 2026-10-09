# Venue shortlist — verified 2026-10-09

Decision context: user chose **B+C framing** (testbed + measurement-failure catalog), **workshop paper, soon**, arXiv preprint. Sources for everything below: workshop website (`trust4rsi-agent.github.io/AAAI2027/`, fetched 2026-10-09) and the OpenReview API (`api2.openreview.net/groups?id=AAAI.org/2027/Workshop/Trust4RSI-Agent`), which agree. Note: the site's template carries leftover "thank you for attending" chrome from a prior edition; the Key Dates and OpenReview submission window (opened Oct 3, 2026) are current and consistent.

## Primary target: Trust4RSI-Agent @ AAAI 2027  ★ near-perfect fit

**AAAI 2027 Workshop on Trustworthy Evolution of AI Agents: An Agent Operating System Perspective**

| | |
|---|---|
| Submission deadline | **November 20, 2026, AoE — strict, "will not be extended"** |
| Notification | December 2, 2026, AoE |
| Workshop date | February 22–23, 2027, Palais des congrès de Montréal (one day, TBA) |
| Format | 8-page full / 4-page short; AAAI 2027 author kit; single PDF; **double-blind** |
| Submission | OpenReview: `AAAI.org/2027/Workshop/Trust4RSI-Agent/-/Submission` |
| Website | https://trust4rsi-agent.github.io/AAAI2027/ |
| Contact | trust4rsi.agent@gmail.com |
| Speakers (so far) | Bengio, Mengdi Wang, Yilun Du, Larochelle, Dawn Song, Koyejo |

**Why it is the right home** — map paper → CFP topics:

- **Their topic (3), "Trustworthy Model and Policy Evolution — the update and release layer":** "Self-improvement as a release process: **versioning of prompts, policies, and weights; staged rollout and canarying; regression suites; rollback** … reliability of self-generated critiques; and **prevention of reward hacking**." — This is Petri's component list almost verbatim: the genome is versioned plain-text policy; the gatekeeper is the regression suite / release gate; canary tasks are canarying; the critic screen is the self-generated-critique reliability check; CS5 is reward-hacking prevention.
- **Their topic (5), "Evaluating Trustworthy Evolution — the observability and audit layer":** "**Structured traces attributing an outcome to the update that caused it**, continuous monitoring rather than one-off benchmarking, oversight interfaces that **escalate before irreversible updates**, and **stateful long-horizon testbeds**." — That is the paper's B+C framing stated as a call: the append-only spine IS the structured trace; CS6 (attribution) is their "attributing an outcome to the update"; human-merge-only promotion IS the escalation-before-irreversible-update; Petri is a stateful testbed.
- CFP explicitly welcomes **"benchmarks, negative results, and position papers"** — the paper is a testbed + a clean null + a failure catalog. Negative results are in the call.

Pitch angle for the abstract's first revision: lead with "self-improvement as a release process" vocabulary (it is theirs) while keeping our measurement-failure catalog as the payload.

## Timeline (working back from Nov 20, 2026 AoE)

- **Oct 9–10**: evolve run resolves → re-gate post hoc, fill §5.3 + CS2 finals, regenerate numbers.md, commit.
- **Oct 16**: complete prose draft (§2 related work from corpus cards, §3 expansions, §6–8, appendices A–C); AAAI-27 workshop CfPs post → re-scan the 47-workshop list for secondary fits.
- **Oct 23–30**: figures built (FIGURES.md); internal revision pass; threats/discussion hardened.
- **Nov 6**: convert to AAAI 2027 author kit (LaTeX); **anonymization pass** (double-blind): strip authors, anonymize repo pointers ("supplementary artifact, anonymized"), check self-citations in third person, remove the fork/worktree paths.
- **Nov 13**: final PDF, checklist pass, buffer week.
- **Nov 20 AoE**: submit.
- **arXiv**: post the preprint **after** submission unless the workshop policy explicitly permits prior preprints (AAAI workshops are generally tolerant of arXiv, but verify on the CFP/OpenReview page before posting — the default plan is arXiv on/after Dec 2 notification).

## Backups (if rejected Dec 2, or missed)

1. **ICLR 2027 workshops** — deadlines historically late Jan–early Feb 2027; workshop lists announce ~Dec 2026. Verify when posted; agent-eval and safety workshops are near-certain to exist. Timing works: rejected Dec 2 → ICLR workshop deadline ~2 months later, results already final.
2. **arXiv preprint regardless** (the user's "arXiv-first" intent is satisfied by posting immediately after the workshop decision either way).
3. **Other AAAI-27 workshops** from the 47-workshop program (re-scan Oct 16 when CfPs post) — secondary fits would be agent-eval or LLM-agents tracks; Trust4RSI-Agent dominates them on fit.
