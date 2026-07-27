# Contributing

## Add a skill

1. Create `skills/<name>/SKILL.md` with frontmatter:

   ```yaml
   ---
   name: <name>
   description: <when the agent should trigger it — verbs + trigger phrases>
   allowed-tools: <tool allowlist — must cover everything the body instructs; validate-skills enforces presence>
   version: "1.0.0"
   ---
   ```

   `name` and `description` are the only fields skills.sh discovery requires; this repo also
   requires `allowed-tools` (a skill whose body demands tools its allowlist forbids is broken by
   construction — that shipped once).

2. Body = the instructions the agent follows. Extra assets (templates, scripts)
   live next to `SKILL.md` in the same directory so they travel with the skill.
   Note: a single-skill skills.sh install carries only that directory — don't rely
   on sibling top-level dirs like `rules/` unless you target the full plugin
   install.

3. Update the skills table in [README.md](README.md).

4. **Do not touch `.claude-plugin/plugin.json` `version`** in a feature PR — the plugin
   version is set automatically from the release tag (see [Release](#release)). Leaving it
   out of feature PRs avoids cross-PR conflicts on the version line.

## Rules: the two tiers, and why code lives in them

A rule has:

1. **A standard** (always) — normative bullets. What must be true. Terse.
2. **A reference implementation** (only where it earns its place) — code that has been **executed**,
   not merely written.

`rules/golang.md` is a page of bullets because Go's standard is self-evident. `rules/postgres.md` carries a
verified engine, a drift test and an e2e recipe because each of those was got *wrong* here first — the
lazy-load N+1, the timeout budget, the `ALTER DEFAULT PRIVILEGES … FOR ROLE` trap. A bullet cannot
convey those; a snippet can.

**Nothing auto-loads rules today.** The `paths:` frontmatter documents which files a rule governs —
declarative metadata for humans and future tooling, not a live mechanism. A rule reaches an agent
through two explicit paths only: a skill references it via `${CLAUDE_PLUGIN_ROOT}/rules/<file>`, and
the shared blocks below inject its code into the skills mechanically. Code belongs in the rule because
the rule is the **canonical copy** — one place to bump, every include follows — not because anything
loads it by glob. (If a hook ever consumes `paths:`, rewrite this paragraph.)

**Code in a rule must have been run.** Not "looks right" — run. Every defect this repo shipped past
review was plausible-looking prose that nobody executed.

## Shared blocks: drift is a CI failure, not a discipline problem

The init skills need to *show* the code, not just point at it. So the code is duplicated — but
**mechanically**, never by hand:

````markdown
rules/python.md              skills/python-init/SKILL.md
<!-- block: fastapi-deps --> <!-- include: rules/python.md#fastapi-deps -->
```toml                      ```toml
...                          ...same bytes, injected...
```                          ```
<!-- /block -->              <!-- /include -->
````

Use a block **only when two or more files genuinely need the same bytes**. A skill that can simply
*point* at its rule (`${CLAUDE_PLUGIN_ROOT}/rules/<file>`) should point — the init skills require the
full plugin install anyway (rules/ present), so "must stand alone" is not a reason to copy.

- `python3 scripts/sync_blocks.py` — **fails if any copy has drifted**, and **fails if a canonical
  block is not a well-formed unit** (unbalanced ``` fences, or fenced `toml`/`python` that does not
  parse — a block boundary must never cut through a fence or a TOML value). Runs inside
  `validate-skills.sh`, so CI runs it on every push.
- `python3 scripts/sync_blocks.py --fix` — regenerates the copies from their canonical blocks.

**The canonical block wins.** Change it there; run `--fix`; commit both. Skills may declare blocks too
(e.g. `skills/my-review/SKILL.md#review-doctrine`, mechanically included by `iterative-review`;
`swarm-review` references it in prose through its per-agent execution mandate) — same mechanism,
same gate.

This exists because "remember to keep them in sync" failed, repeatedly: `fastapi>=0.115` vs `>=0.118`,
four different `useradd` invocations, two divergent Dockerfiles. Enforce constraints with CI, not with
instructions — the same rule `rules/agents-md.md` gives you.

## Add or change a rule

1. Create `rules/<topic>.md` with `paths:` frontmatter — the globs it applies to:

   ```yaml
   ---
   paths: **/*.py,**/pyproject.toml
   ---
   ```

2. Reference it from the skills that need it, **one explicit path per reference**:
   `${CLAUDE_PLUGIN_ROOT}/rules/<topic>.md`. Never brace-expand (`rules/{a,b}.md`) —
   `scripts/validate-skills.sh` cannot see those, so a typo'd rule would pass CI silently.
   A rule may also point at a sibling rule with a bare `rules/<topic>.md` path (e.g.
   `python.md` → `rules/design.md`); both forms are gate-checked for existence.

   **To point at a *section*, one form only** — the path, then the heading in parentheses and
   double quotes. Works for a rule or for another skill:

   ```markdown
   Copy the template from `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` ("Go build") verbatim.
   The canonical evidence bar lives in `skills/my-review/SKILL.md` ("The evidence bar").
   ```

   Matched as a substring of the target's markdown headings — so the heading may carry a trailing
   `(canonical for …)` — and it must match **exactly one**. Neither side counts `#` lines inside
   YAML frontmatter or inside ``` / ~~~ fences, so a pointer shown *as an example* in a fence is
   documentation, not a live pointer. The gate keys on the *path*: a `("…")` parenthetical is only a
   pointer when a `rules/<file>.md` or `skills/<name>/<file>.md` path precedes it, so ordinary prose
   like ``` `zap`'s "sugared" logger ``` is not checked. Line wraps between the path and the
   parenthetical are tolerated, and curly quotes are normalised.

   Sources scanned: `skills/**.md`, `rules/**.md`, and this file. Bare references (no section) are
   existence-checked too, for both `rules/<file>.md` and `skills/<name>/SKILL.md`.
3. If a skill must *show* the rule's code, wrap it in a `<!-- block: -->` and include it (above).
4. `bash scripts/validate-skills.sh` must pass.

**One pairing is gated by identifier set rather than by block or pointer**: the Go build-time var
block in `rules/golang.md` and the copy inside `go-init`'s `main.go` template must declare the *same
identifiers* (check 2c). They cannot be a shared block — the skill's copy lives inside a ```go fence,
where `<!-- include: -->` markers would end up in the generated `.go` file — so the gate compares
names, not bytes: indentation and default values may differ, the set may not. Restructuring either
`var ( … )` block away fails the gate rather than silently disabling it.

## Release

The plugin version is owned by the release **tag**, not by PRs. To cut a release:

1. Merge the feature PR(s) to `master`.
2. Push a semver tag: `git tag v1.2.0 && git push origin v1.2.0`.

The `release` workflow then writes `1.2.0` into `.claude-plugin/plugin.json` on `master`
(`chore(release): v1.2.0`) and publishes a GitHub release. Consumers with `autoUpdate: true`
pick up the new `master` at next Claude Code startup.

## Setup (once per clone)

```bash
pre-commit install   # the local hooks gate every commit; CI runs them too, but later is worse
```

## Test before opening a PR

```bash
# Load the plugin from your working tree in a throwaway session
claude --plugin-dir .

# Validate the marketplace + plugin manifests (offline, no API key)
claude plugin validate .

# What CI runs — the local hook invokes scripts/validate-skills.sh: frontmatter; rule and skill
# references AND the sections they point at; the Go build-var set agreeing between rules/golang.md
# and go-init; block drift incl. both gates' own unit tests; pin uniformity; retired md2clip command
# forms plus md2clip --selftest; the review templates' finding typography
pre-commit run --all-files
```

## PR flow

Branch, commit ([Conventional Commits](https://www.conventionalcommits.org/)), push,
open a PR. CI runs `claude plugin validate .` on every push and PR. Once merged to
`master`, consumers with `autoUpdate: true` pick it up at next Claude Code startup.
