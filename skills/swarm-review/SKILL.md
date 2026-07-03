---
name: swarm-review
description: Multi-perspective parallel review of changes by dispatching one focused agent per angle (security, resiliency, code quality, functional, documentation, global coherence, tests/coverage), then consolidating findings. Use when the user asks for a "swarm review", "multi-angle review", "parallel review", "review from all perspectives", or `/swarm-review`.
allowed-tools: Bash(git diff *), Bash(git status *), Bash(git log *), Bash(git rev-parse *), Bash(git merge-base *), Bash(git branch *), Bash(gh pr *), Bash(glab mr view *), Bash(glab mr diff *), Read, Grep, Glob, Agent
version: "1.0.1"
---

# Swarm Review

Dispatch **seven** parallel review agents over the same scope, each with a single, focused lens. Consolidate their findings into one prioritised report.

This skill is the parallel, lens-per-agent counterpart of `my-review` (which does everything in one pass). Prefer this when changes are large or risk-sensitive enough that depth-per-axis matters more than reviewer-token cost.

## Scope resolution

Determine the scope **before** spawning agents:

1. If the user passed an explicit scope, use it. Accepted forms:
   - paths/globs (`src/foo/**`)
   - a branch range (`main..HEAD`, `origin/develop...HEAD`)
   - a PR number (`#123` or `PR 123`) — resolve via `gh pr diff <n>` and `gh pr view <n>`
   - a commit range (`<sha>..<sha>`)
2. Otherwise default to the working diff:
   - find the base: first of `origin/develop`, `origin/trunk`, `origin/main`, `origin/master` that exists via `git rev-parse --verify`
   - compute `git merge-base <base> HEAD`, then `git diff <merge-base>...HEAD` plus uncommitted (`git diff HEAD` and `git status --porcelain`)
3. Capture the **exact diff text**, the **list of changed files**, and a **one-paragraph change summary** (read commit messages + skim diff). All three are passed verbatim to every subagent so they share context without re-deriving it.

If the scope is empty (no diff, no files), stop and tell the user — don't spawn agents over nothing.

## Spawn the swarm

Send **one** message with **seven** `Agent` tool uses in parallel. Use `subagent_type: "general-purpose"` (read-only investigation, full tool access for grep/read/web). Each prompt must be self-contained: the agent has no view of this conversation.

For every agent, the prompt MUST include:

- **Role line** — e.g. *"You are the security reviewer in a multi-agent swarm. Stay strictly within your lens; other agents cover the rest."*
- **Stance line** — the lens-specific operating assumption from the table below. This is **not** a persona ("act grumpy"); it's a frame that biases what the agent prioritises without distorting tone. Include it verbatim in the prompt.
- **Scope block** — the diff, the changed-files list, and the change summary from the step above.
- **Lens checklist** — the specific items from the table below for that perspective.
- **Output contract** — must return findings using the template in `template.md` (severity-graded: Critical / High / Medium / Low / Positive), with `file:line` for every finding. No prose preamble. Do **not** number findings (the consolidator assigns IDs after dedup).
- **Boundary reminder** — *"If a finding sits on the border of another lens, mention it once and tag `[overlap:<lens>]`; do not expand into that lens."*

### The seven lenses

| Lens | Stance (operating assumption) | Focus |
|---|---|---|
| **security** | *"Assume an adversary reads this code looking for ways to abuse it. What's the cheapest exploit?"* | Input validation, injection (SQL/cmd/template/XSS), authn/authz, secrets in code or logs, crypto misuse, SSRF, deserialization, dependency CVEs touched by the diff, least-privilege regressions. Map findings to OWASP Top 10 / OWASP API Security Top 10 categories and cite CWE IDs; use OWASP ASVS as the checklist for verification depth |
| **resiliency** | *"Assume this runs at 3 AM during a partial outage. What fails first, and does failure stay contained?"* | Error handling, retry/backoff, timeouts, idempotency, partial-failure paths, resource cleanup, circuit breakers, graceful degradation, race conditions, concurrency, blast radius of failures |
| **code-quality** | *"Assume a tired teammate inherits this in 6 months. Where will they stumble?"* | Readability, complexity, duplication, dead code, naming, language idioms, simplicity-vs-cleverness, abstraction fit, comments-explain-WHY |
| **functional** | *"Assume the spec/ticket is what users actually need. Does the code do that, or something adjacent?"* | Does the change actually solve the stated problem? Edge cases, off-by-one, boundary conditions, regressions in adjacent features, behavior under empty/null/large inputs |
| **documentation** | *"Assume the only thing a new user has is the docs. Can they succeed?"* | README, ADRs, API/OpenAPI specs, CLI `--help`, code comments WHERE they explain WHY, CHANGELOG, migration notes; accuracy vs. the new code |
| **global-coherence** | *"Assume the repo already has the utilities and patterns this needs. Did the author find them, or build a parallel one?"* | Architectural fit, naming/module conventions consistent with the rest of the repo, no parallel implementations of existing utilities, layering respected, public surface kept small |
| **tests-coverage** | *"Assume someone refactors this next sprint without reading the tests. Will the tests catch the breakage?"* | Are new code paths tested? Are edge cases covered? Test quality (no over-mocking, deterministic, fast), missing regression tests for the bug being fixed, coverage of error paths |

## Consolidate

Once all seven agents return:

1. **Merge** findings into a single report grouped by severity (Critical → Low → Positive), each finding tagged with its source lens, e.g. `[security] SQL string built via concatenation src/db.py:42`.
2. **Deduplicate** — if two lenses raised the same `file:line` with the same root cause, keep one entry and list both lens tags.
3. **Assign stable IDs** during consolidation (`C1, C2, … H1, H2, …`) so the user can reference findings in follow-up (`"apply C1 and H3"`). Subagents do **not** number their own findings — numbering is the consolidator's job after dedup.
4. **Top of report**: 2-3 sentence executive summary + a one-line verdict (`ship`, `ship-with-followups`, `block`).
5. **Bottom of report**: per-lens micro-summary (one line each) so the user can see whether any lens came back clean vs. noisy.
6. Use the format in [template.md](template.md).

## Output discipline

- Never invent line numbers — if an agent returns a finding without `file:line`, drop it or ask that agent to re-run with locations.
- Don't flood with style nits when logic/security bugs exist — surface those first.
- If a lens returned nothing, write `None.` under it; do not pad.
- Cite the scope at the top of the report so the user can reproduce: base ref, head ref, changed-file count.
