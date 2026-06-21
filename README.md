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

## Skills

Invoked bare (`/smart-commit`) or namespaced (`/babs:smart-commit`) when a name
collides with another plugin.

### Project init

| Skill | Invocation | Description |
|-------|-----------|-------------|
| `dockerfile-init` | `/dockerfile-init` | Generate a production Dockerfile or align an existing one to the standard |
| `go-init` | `/go-init` | Initialize a new Go HTTP service or align an existing one to the standard |
| `python-init` | `/python-init` | Initialize a new Python FastAPI project or align an existing one to the standard |

### Implement

| Skill | Invocation | Description |
|-------|-----------|-------------|
| `implement-loop` | `/implement-loop` | Autonomous multi-phase build loop from a handoff/plan/ticket: dev → test + dual guards → review → address (edge cases) → coherence → commit → repeat, with per-phase DoD, escalation on design forks, and a human merge gate |

### Review → commit

| Skill | Invocation | Description |
|-------|-----------|-------------|
| `my-review` | `/my-review` | Thorough review of all project changes |
| `iterative-review` | `/iterative-review` | Iterate review + fix rounds on changed code until the tree is clean |
| `swarm-review` | `/swarm-review` | Multi-perspective parallel review: one focused agent per angle (security, resiliency, quality, functional, docs, coherence, tests), then consolidated findings |
| `smart-commit` | `/smart-commit` | Interactive branch, conventional commit, and push with user validation |

### Tools / helpers

| Skill | Invocation | Description |
|-------|-----------|-------------|
| `privatebin` | `/privatebin` | Upload text or a file to PrivateBin, returning both the share URL and the delete URL |
| `md-to-html-clipboard` | `/md-to-html-clipboard` | Render Markdown to HTML into the system clipboard for paste into Teams/Outlook/Confluence |

## Caveat — init skills need `rules/`

`dockerfile-init`, `go-init`, and `python-init` read shared standards from
`rules/*.md` via `${CLAUDE_PLUGIN_ROOT}`. That variable is only set on a **full
plugin install** (the Claude Code path above), where the whole repo — including
`rules/` — is present. A standalone single-skill install via skills.sh installs only
that skill's directory and **won't** carry the sibling `rules/`, so those three
skills are best used through the Claude plugin install.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
