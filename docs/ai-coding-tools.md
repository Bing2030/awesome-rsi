# AI Coding Toolchain — Design & Utilization Guide

How to run **Claude Code**, **OpenCode**, and **Cursor** together on one machine,
against one model gateway, on one repository — without the tools fighting each
other.

Written for this machine's setup: macOS, zsh, and an Anthropic-protocol gateway
(Claude Code currently reaches it through `ANTHROPIC_BASE_URL` /
`ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`).

---

## 1. The three tools at a glance

| | Claude Code | OpenCode | Cursor |
|---|---|---|---|
| Form | Terminal agent (CLI) + IDE extensions | Open-source terminal agent (TUI) + desktop app | AI-first code editor (VS Code fork) + CLI |
| Best at | Long autonomous tasks, plan mode, background work, deep repo refactors | Same class of work as Claude Code, fully open-source, any provider via config | Editor-native editing, inline Tab completions, multi-file GUI diffs, reviewing agent output |
| Auth | Anthropic account **or** gateway env vars | Per-provider API keys **or** custom provider JSON | Cursor subscription **or** BYO API keys |
| Project rules file | `CLAUDE.md` (+ `.claude/`) | `AGENTS.md` (+ `~/.config/opencode/AGENTS.md` global) | `.cursor/rules/*.mdc` (+ `AGENTS.md` in recent versions) |
| Custom Anthropic-protocol gateway | Native (env vars) | Via custom provider in `opencode.json` | Not directly (custom base URL is OpenAI-protocol); use subscription or a direct key |
| Headless / automation | `claude -p "..."` | `opencode run "..."` | Cursor CLI (`cursor-agent`) + Cursor Action for GitHub Actions |

Design stance: **they are interchangeable workers over a shared contract** —
same repo, same rules file, same test gate, same gateway. Pick per task, not
per loyalty.

---

## 2. Design principles

1. **One source of truth for instructions.** All three read a project
   instructions file, but with different default names. Keep `AGENTS.md` as
   the canonical file and point the others at it (symlinks — §5). Never
   maintain three divergent copies.
2. **Gateway-centered auth.** Models are reached through one gateway; each
   tool is just a different client of it. Credentials live in the
   environment / per-tool config, never in the repo.
3. **One agent per working tree.** Two agents editing the same files
   concurrently corrupt each other's work. Either serialize (handoff
   protocol, §6.3) or isolate (one git worktree per tool, §6.2).
4. **The test suite is the arbiter.** The agents may differ; the definition
   of "correct" does not. In this repo that means `uv run pytest -q` in
   `framework/` (offline, deterministic) — every agent's output is judged by
   the same command before commit.
5. **Explicit cost and permission ceilings per tool.** Each tool has its own
   spend and approval controls (§7). Set them once, centrally, not ad hoc
   per session.

---

## 3. Installation & setup (macOS / zsh)

### 3.1 Claude Code (already installed on this machine)

```bash
curl -fsSL https://claude.ai/install.sh | bash   # native installer
# or: npm i -g @anthropic-ai/claude-code
```

Gateway routing (already active here — shown for reference):

```zsh
# ~/.zshrc
export ANTHROPIC_BASE_URL="https://<your-gateway-host>"   # Anthropic-protocol endpoint
export ANTHROPIC_AUTH_TOKEN="<token>"                     # gateway credential
export ANTHROPIC_MODEL="glm-5.3"                          # default model override
```

Verify: `claude --version`, then inside a repo run `claude` and `/model` to
confirm the routed model.

### 3.2 OpenCode

```bash
curl -fsSL https://opencode.ai/install | bash
# or: brew install sst/tap/opencode
# or: npm i -g opencode-ai
```

Built-in providers: `opencode auth login` and pick one (Anthropic, OpenAI,
Google, OpenRouter, Ollama for local models, ...).

**Custom provider for the gateway** — `~/.config/opencode/opencode.json`
(OpenCode does not read Claude Code's env vars for this):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "my-gateway": {
      "npm": "@ai-sdk/anthropic",
      "name": "Anthropic-protocol gateway",
      "options": {
        "apiKey": "{env:ANTHROPIC_AUTH_TOKEN}",
        "baseURL": "{env:ANTHROPIC_BASE_URL}"
      },
      "models": {
        "glm-5.3": {},
        "glm-5.3-flash": {}
      }
    }
  }
}
```

(`{env:VAR}` interpolation keeps the token out of the file. For an
OpenAI-protocol endpoint instead, use `"npm": "@ai-sdk/openai-compatible"`
with its `baseURL` — same shape.)

Then register the credential once so the picker shows it:

```bash
opencode auth login   # choose "Other" -> my-gateway, paste the key (or rely on {env:})
```

Run `opencode` in a repo; press `~` to open the model picker and select
`my-gateway/glm-5.3`. Non-interactive use: `opencode run "fix the failing test"`.

### 3.3 Cursor

```text
1. Download from https://cursor.com, move to /Applications, sign in.
2. Cursor menu -> "Install shell command"  ->  `cursor .` opens a folder.
3. Settings -> Models: keep the subscription models, or enable API-key
   overrides (direct Anthropic/OpenAI keys; custom base URLs are
   OpenAI-protocol only).
4. Enable Agent mode in the chat panel for multi-file edits.
```

Terminal agent (same account):

```bash
curl https://cursor.com/install | bash     # installs the Cursor CLI
# see https://cursor.com/docs/en/cli/installation for the current binary
# name (cursor-agent / cursor) and login flow
```

For CI, the official **Cursor Action** on the GitHub Marketplace runs the
same agent on `ubuntu/macos/windows-latest` with a stored token.

Optional but recommended: install the **Claude Code** and **OpenCode**
extensions inside Cursor, so both terminal agents are also available from
the editor's panel instead of only in a shell.

---

## 4. Model routing reference

| Purpose | Env / config | Where |
|---|---|---|
| Claude Code gateway | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL` | shell env |
| OpenCode gateway | `provider.my-gateway` block | `~/.config/opencode/opencode.json` |
| OpenCode per-project overrides | `opencode.json` in repo root (gitignored if it carries nothing secret) | project |
| Cursor models | Settings → Models (subscription or BYO keys) | app |
| Cursor CLI auth | docs-managed token/login | per CLI docs |

Suggested routing: use the strong default (`glm-5.3`) for interactive work
in all clients; route the cheap variant (`glm-5.3-flash`) to background
chores (doc regeneration, test triage) where a tool lets you pick per task.

---

## 5. Shared project rules (single source of truth)

```bash
cd ~/Documents/projects/awesome-rsi
$EDITOR AGENTS.md          # canonical rules, see template below
ln -sf AGENTS.md CLAUDE.md # Claude Code reads CLAUDE.md
mkdir -p .cursor/rules     # Cursor reads .cursor/rules (+ recent versions
                           # also read AGENTS.md directly)
```

`.gitignore`: keep `AGENTS.md` and `CLAUDE.md` tracked (a symlink commits
fine); ignore any local-only `opencode.json` if you add one.

**Template `AGENTS.md` for this repo:**

```markdown
# Project rules — awesome-rsi

## Layout
- `framework/` — the rsif framework (src, tests, docs). All code work happens here.
- `site/`, `resources/`, list content — READ-ONLY reference material; never modify.

## Commands (run inside framework/)
- `uv run pytest -q` — offline deterministic suite; must be green before any commit.
- `uv run pytest -m live` — spends real gateway budget; only when explicitly asked.
- `RSIF_UPDATE_GOLDEN=1 uv run pytest tests/golden` — regenerate goldens deliberately,
  never silently; say so in the commit message if you do.
- `uv run rsif init/evolve/status/report ...` — see framework/docs/quickstart.md.

## Conventions
- Verify claims against `site/curated.json` and the PDFs in `resources/` before
  citing arXiv IDs.
- Update framework/docs/plan.md status + decision-log.md for any design change.
- Determinism is a hard requirement: no wall-times/randomness in event payloads.
```

Global, machine-wide preferences (coding style, pronouns, tone) belong in
each tool's global config instead: `~/.claude/CLAUDE.md`,
`~/.config/opencode/AGENTS.md`, Cursor Settings → Rules → User Rules.

---

## 6. Utilization playbook

### 6.1 Which tool for which job

| Task | Tool | Why |
|---|---|---|
| Explore / navigate a large unfamiliar repo | Cursor | GUI search, go-to, multi-pane reading |
| Small surgical edits, completions | Cursor (inline/Tab) | Lowest latency, editor-native |
| Medium feature with unclear shape | Claude Code (plan mode first) | Interactive plan → approval → implement |
| Long autonomous run (refactor, milestone) | Claude Code or OpenCode | Terminal agents, background tasks, no GUI needed |
| Same task, second opinion | The *other* terminal agent | Different harness strengths; same rules + tests |
| Scheduled / CI automation | `claude -p`, `opencode run`, Cursor Action | Headless modes |
| Reviewing a big agent-produced diff | Cursor (GUI diff) or `claude` review pass | Human-readable presentation |

### 6.2 Parallel work: one worktree per tool

```bash
cd ~/Documents/projects/awesome-rsi
git worktree add ../awesome-rsi-cursor  main       # or a feature branch
git worktree add ../awesome-rsi-opencode main
# Cursor opens ../awesome-rsi-cursor, OpenCode runs in ../awesome-rsi-opencode,
# Claude Code stays in the main checkout.
```

Rules of the road:

- Each worktree = one agent = one branch. Merge through PRs or fast-forward
  merges from the main checkout.
- Worktrees share one `.git`; `git worktree list` is the roster,
  `git worktree remove` cleans up.
- Remember `framework/.venv` and `framework/.pytest_cache` are per-worktree —
  run `uv sync` once in each new worktree.

### 6.3 Serial work: handoff protocol (single checkout)

1. Before handing off: `git status` must be clean (commit or stash).
2. Agent B starts from a known revision; read `git log -3` for context.
3. After B finishes: run the test gate (`uv run pytest -q`), review the diff,
   commit.
4. Never leave two agents running against the same checkout — including a
   Cursor agent chat left open while a CLI agent works.

### 6.4 MCP servers (shared capability, per-tool wiring)

Any MCP server (e.g. a codegraph indexer for this repo) must be registered
per tool:

- Claude Code: `claude mcp add <name> -- <command>` (or `.mcp.json` in the
  repo — this file IS shareable/committable).
- OpenCode: `opencode.json` → `"mcp"` block, same server command.
- Cursor: Settings → MCP → Add server.

Tip: keep the canonical server definition in `.mcp.json` at the repo root
and point the other tools' configs at the same command.

### 6.5 Headless / automation snippets

```bash
# Claude Code, one-shot
claude -p "run the offline test suite and summarize failures" --output-format json

# OpenCode, one-shot
opencode run "regenerate the task-pack docs, commit with a clear message"

# Nightly review (cron), either CLI
claude -p "review the last 24h of commits for determinism violations in framework/"
```

In CI, prefer the Cursor Action (GitHub Marketplace) or run either CLI in a
job with the gateway token as a masked secret — never echo it.

---

## 7. Cost, safety, hygiene

| Control | Claude Code | OpenCode | Cursor |
|---|---|---|---|
| Spend ceiling | per-session budgets; gateway-side quotas | model/provider quotas | plan limits or BYO keys |
| Approval gates | permission modes (plan mode, per-tool allow lists) | agent permissions in config | agent mode confirmations / auto-run settings |
| Secrets | env vars only; never in repo | `{env:VAR}` in config | app settings |
| Determinism check | shared: `uv run pytest -q` | same | same |

Hygiene rules:

- The gateway token appears in exactly two places: the shell env and
  OpenCode's config via `{env:...}` interpolation. `grep -r` the repo before
  committing if in doubt.
- Goldens: regenerating `framework/tests/golden/` is a deliberate act
  (`RSIF_UPDATE_GOLDEN=1`), stated in the commit message — true regardless
  of which agent did it.
- Live tests (`pytest -m live`) spend real money; an agent must never decide
  on its own to run them.

---

## 8. Troubleshooting quick reference

| Symptom | Likely cause / fix |
|---|---|
| Claude Code hits a different model than expected | `ANTHROPIC_MODEL` overrides; check `/model` in-session |
| OpenCode doesn't show the custom provider | typo in `opencode.json` (`opencode` surfaces config errors on startup); run `opencode auth login` → "Other" |
| Gateway 4xx in one tool but not others | credential scoping — compare exact env vars the tool reads; Anthropic-protocol vs OpenAI-protocol mismatch |
| Two agents clobbered each other's edits | same working tree — see §6.2/§6.3; recover via `git status`, worktree discipline |
| Cursor CLI hangs after finishing a task in CI | known CI quirk; check Cursor forum / use a timeout wrapper |
| Symlinked `CLAUDE.md` shows as changed after edits | edit `AGENTS.md` (the target), never the symlink; `git diff` shows the canonical file |

---

## 9. References

- OpenCode — site & docs: https://opencode.ai (install: https://opencode.ai/install;
  providers & custom provider config; `AGENTS.md`)
- Claude Code — install & docs: https://claude.ai/install.sh,
  https://docs.claude.com/en/docs/claude-code
- Cursor — https://cursor.com; CLI docs:
  https://cursor.com/docs/en/cli/installation; Cursor Action on GitHub Marketplace
