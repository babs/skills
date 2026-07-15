# skills

A set of Claude Code skills, packaged so they install **two ways** from the same
repo:

- as a **Claude Code plugin/marketplace** (`claude plugin ...`), and
- as **[skills.sh](https://skills.sh)** skills (`npx skills add ...`) — usable from
  Claude Code, Cursor, Codex, and any agent that reads the `SKILL.md` standard.

The repo root *is* the plugin: `.claude-plugin/` holds the manifests and
`skills/<name>/SKILL.md` is both the Claude plugin skills directory and skills.sh's
flat discovery layout.

## Install

### Claude Code (plugin)

```bash
claude plugin marketplace add babs/skills
claude plugin install babs@babs-skills
```

`babs/skills` is GitHub shorthand; the full URL
`https://github.com/babs/skills.git` works too.

#### Auto-update (recommended)

Third-party marketplaces have background auto-update **disabled by default**. Enable
it via the UI (`/plugin` → **Marketplaces** → `babs-skills` → **Enable auto-update**)
or:

```bash
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
jq '.extraKnownMarketplaces["babs-skills"].autoUpdate = true' "$CFG" > "$CFG.tmp" && mv "$CFG.tmp" "$CFG"
```

Manual fallback anytime: `claude plugin update babs`.

### skills.sh (any agent)

```bash
npx skills add babs/skills
```

This installs the `SKILL.md` files into the right per-agent skills directory
(`~/.claude/skills`, `~/.cursor/skills`, …) with cross-agent path detection.

## Status line (optional)

A width-adaptive Claude Code status line ships at
`statusline/statusline-command.sh`:

```
~/path (git::branch) | model | ctx: 26k/200k (13%) | q: 5h24% ⟳17:32
```

`q:` is the 5-hour quota window (used % + local reset time) from `rate_limits`
— shown only for Pro/Max subscribers and only after the first API response;
it colours yellow ≥75%, red ≥90%, and disappears entirely otherwise. The line
also shows a profile badge when `CLAUDE_CONFIG_DIR` points at a custom
`~/.claude-<profile>`.

Plugins can't set `statusLine`, and `statusLine.command` does **not** expand
`${CLAUDE_PLUGIN_ROOT}` — nor is the plugin cache path stable across updates. So
copy the script to a fixed location and point your settings at that path:

```bash
install -m 755 statusline/statusline-command.sh ~/.claude/statusline-command.sh

CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
jq '.statusLine = {type: "command", command: "bash ~/.claude/statusline-command.sh"}' \
  "$CFG" > "$CFG.tmp" && mv "$CFG.tmp" "$CFG"
```

The script only ships with the full plugin install or a repo clone (a
single-skill skills.sh install won't carry it). The reset clock uses GNU `date`;
on macOS/BSD it's silently omitted while the percentage still shows.

## Skills

Invoked bare (`/smart-commit`) or namespaced (`/babs:smart-commit`) when a name
collides with another plugin.

> **Auto-triggering:** these skills carry trigger phrases in their descriptions, so
> the agent invokes them on matching intent without an explicit slash command — e.g.
> asking to commit routes through `smart-commit`, writing a Dockerfile routes through
> `dockerfile-init`. Installing the plugin therefore steers commits, reviews, and
> project scaffolding through these flows in every session. This is safe for
> mutating flows because the skills gate every git mutation interactively before
> running it. To opt out, disable the plugin, or block a single skill with a
> permissions deny rule, e.g. `"deny": ["Skill(skill:*smart-commit)"]`.

### Project init

| Skill | Invocation | Description |
|-------|-----------|-------------|
| `dockerfile-init` | `/dockerfile-init` | Generate a production Dockerfile or align an existing one to the standard; auto-triggers on Dockerfile creation intent |
| `fullstack-init` | `/fullstack-init` | Initialize a FastAPI + PostgreSQL + React project (single image — the SPA is built and served by the backend), or align an existing one; auto-triggers on new-full-stack-app intent |
| `go-init` | `/go-init` | Initialize a new Go HTTP service or align an existing one to the standard; auto-triggers on new-Go-service intent |
| `python-init` | `/python-init` | Initialize a plain Python FastAPI service — no database, no UI (those go to `fullstack-init`) — or align an existing one; auto-triggers on new-Python-project intent |

### Spec → implement

| Skill | Invocation | Description |
|-------|-----------|-------------|
| `spec-feature` | `/spec-feature` | Turn a feature request into `specs/NNN-slug.md` — problem, scope, out-of-scope, acceptance criteria, phases with a measurable DoD — before any code; auto-triggers when a feature is proposed |
| `ship-feature` | `/ship-feature` | Human-paced quality loop against an approved spec: implement → tests → my-review → fix ALL findings → re-review until clean → swarm-review when large → tests + coverage → smart-commit |
| `implement-loop` | `/implement-loop` | Autonomous multi-phase build loop from a handoff/plan/ticket: dev → test + dual guards → review → address (edge cases) → coherence → commit → repeat, with per-phase DoD, front-loaded questions, optional isolated git worktree, escalation on design forks, and a human merge gate |

### Review → commit

| Skill | Invocation | Description |
|-------|-----------|-------------|
| `my-review` | `/my-review` | Thorough review of all project changes; auto-triggers before committing feature work |
| `iterative-review` | `/iterative-review` | Iterate review + fix rounds on changed code until the tree is clean |
| `swarm-review` | `/swarm-review` | Multi-perspective parallel review: one focused agent per angle (security, resiliency, quality, functional, docs, coherence, tests), then consolidated findings |
| `smart-commit` | `/smart-commit` | Interactive branch, conventional commit, and push with user validation; auto-triggers on any commit intent in interactive sessions |

### Tools / helpers

| Skill | Invocation | Description |
|-------|-----------|-------------|
| `privatebin` | `/privatebin` | Upload text or a file to PrivateBin, returning both the share URL and the delete URL |
| `md-to-html-clipboard` | `/md-to-html-clipboard` | Render Markdown to HTML into the system clipboard for paste into Teams/Outlook/Confluence |

## Caveat — init skills need `rules/`

`dockerfile-init`, `fullstack-init`, `go-init`, and `python-init` read shared standards from
`rules/*.md` via `${CLAUDE_PLUGIN_ROOT}`. That variable is only set on a **full
plugin install** (the Claude Code path above), where the whole repo — including
`rules/` — is present. A standalone single-skill install via skills.sh installs only
that skill's directory and **won't** carry the sibling `rules/`, so those four
skills are best used through the Claude plugin install.

## Caveat — `fullstack-init` vendors an external tool

Projects scaffolded by `fullstack-init` run their database migrations with
[babs/db_migrate](https://github.com/babs/db_migrate) — a single file fetched **at a pinned commit SHA**
(recorded in the vendoring commit) and committed into the project, so the shipped version is whatever
your repo holds. It is not a PyPI dependency. It executes DDL with the migration credential, so diff
it on every upgrade like any other code.
Its [`llms.txt`](https://github.com/babs/db_migrate/blob/master/llms.txt) is the agent-facing usage
reference (linked at `master` for readability — the runtime copy itself is SHA-pinned).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
