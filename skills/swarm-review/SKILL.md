---
name: swarm-review
description: Multi-perspective parallel review of changes by dispatching one focused agent per angle (security, resiliency, code quality, functional, documentation, global coherence, tests/coverage), then consolidating findings. Use when the user asks for a "swarm review", "multi-angle review", "parallel review", "review from all perspectives", or `/swarm-review`.
allowed-tools: Bash(git diff *), Bash(git status *), Bash(git log *), Bash(git rev-parse *), Bash(git merge-base *), Bash(git branch *), Bash(gh pr *), Bash(glab mr view *), Bash(glab mr diff *), Read, Grep, Glob, Agent, SendMessage
version: "1.6.0"
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
4. The unit of review is the **feature**, not the diff at hand: when the user narrows the scope (one commit, a path subset) on the checked-out branch, also resolve `<merge-base>...HEAD` and pass it as feature context. For a PR scope take the PR's own base — `gh pr view <n> --json baseRefName` — never the local `HEAD`, which is a different branch. Canonical: `skills/my-review/SKILL.md` ("Scope on a feature branch").

If the scope is empty (no diff, no files), stop and tell the user — don't spawn agents over nothing.

## Spawn the swarm

Send **one** message with **seven** `Agent` tool uses in parallel. Use `subagent_type: "general-purpose"` (read-only investigation, full tool access for grep/read/web). Each prompt must be self-contained: the agent has no view of this conversation.

Pass `run_in_background: false` on all seven — when the harness honours it, each call returns its lens report as the tool result, which is the cleanest collection path. **Do not assume it took.** A spawn result saying the agent is now running, or that it will receive instructions via its mailbox, means the call was backgrounded regardless and that report will arrive later as a message. Read each spawn result and know which mode you are in: background agents report through notifications that arrive interleaved, out of order, and alongside idle/availability events that look like completion but carry no findings. The collection ledger below is what makes either mode safe — it is not optional in the synchronous case either.

For every agent, the prompt MUST include:

- **Role line** — e.g. *"You are the security reviewer in a multi-agent swarm. Stay strictly within your lens; other agents cover the rest."*
- **Stance line** — the lens-specific operating assumption from the table below. This is **not** a persona ("act grumpy"); it's a frame that biases what the agent prioritises without distorting tone. Include it verbatim in the prompt.
- **Scope block** — the diff, the changed-files list, the change summary, and the feature-wide context from the step above, with the instruction: *"review the feature as a whole, not the hunk; a defect an earlier commit of the branch introduced is in scope, and every fix must be right for the whole feature."*
- **Lens checklist** — the specific items from the table below for that perspective.
- **Output contract** — must return findings using the template in `template.md` (severity-graded: Critical / High / Medium / Low / Positive), with `file:line` and a tiered fix line (`→ **Fix (inst|class):**`, canonical: `skills/my-review/SKILL.md` ("The fix bar")) for every finding, plus a **complexity index** for the fix: `cx:S` (localized — one line / one file, no design impact), `cx:M` (multi-site, or needs a new test / small refactor), `cx:L` (design-level or cross-cutting change). Severity says how much it hurts; complexity says how much it costs to fix — report both, never let one influence the other. No prose preamble. Do **not** number findings (the consolidator assigns IDs after dedup).
- **Delivery channel** — *"Your report is your final message. If you are running in the background, deliver it with `SendMessage` to `main` — plain output does not reach the consolidator. If you did not run the analysis, say exactly that; a stated 'did not run' beats a report reconstructed from memory."*
- **Boundary reminder** — *"If a finding sits on the border of another lens, mention it once and tag `[overlap:<lens>]`; do not expand into that lens."*
- **Execution mandate** — *"Prefer running over reading. If the code can be executed, execute it: run the
  suite, build the image, curl the endpoint, break the guard and confirm it fails. Every Critical/High
  must carry the command and the output you observed, or be labelled `[unverified]`."* Give the agents
  whatever they need to do that: a scratch dir, the repo path, whether `docker`/`make`/network are
  available. **A swarm that only reads is a swarm of plausible opinions** — and plausible opinions are
  precisely what shipped the last six defects.
- **Prior-round context** (re-reviews only) — list what the previous round fixed, and instruct: *"verify
  those fixes hold; hunt for what they introduced."* Fixes are unreviewed code.

### The seven lenses

| Lens | Stance (operating assumption) | Focus |
|---|---|---|
| **security** | *"Assume an adversary reads this code looking for ways to abuse it. What's the cheapest exploit?"* | Input validation, injection (SQL/cmd/template/XSS), authn/authz, secrets in code or logs, crypto misuse, SSRF, deserialization, dependency CVEs touched by the diff, least-privilege regressions. Map findings to OWASP Top 10 / OWASP API Security Top 10 categories and cite CWE IDs; use OWASP ASVS as the checklist for verification depth |
| **resiliency** | *"Assume this runs at 3 AM during a partial outage. What fails first, and does failure stay contained?"* | Error handling, retry/backoff, timeouts, idempotency, partial-failure paths, resource cleanup, circuit breakers, graceful degradation, race conditions, concurrency, blast radius of failures |
| **code-quality** | *"Assume a tired teammate inherits this in 6 months. Where will they stumble?"* | Readability, complexity, duplication, dead code, naming, language idioms, simplicity-vs-cleverness, abstraction fit, comments stating a constraint the code cannot show — rationale for a choice belongs in the commit message, and a six-line comment wall over a two-line change is a finding |
| **functional** | *"Assume the spec/ticket is what users actually need. Does the code do that, or something adjacent?"* | Does the change actually solve the stated problem? Edge cases, off-by-one, boundary conditions, regressions in adjacent features, behavior under empty/null/large inputs |
| **documentation** | *"Assume the only thing a new user has is the docs. Can they succeed?"* | README, ADRs, API/OpenAPI specs, CLI `--help`, code comments where they state a constraint the code cannot show, CHANGELOG, migration notes; accuracy vs. the new code |
| **global-coherence** | *"Assume the repo already has the utilities and patterns this needs. Did the author find them, or build a parallel one?"* | Architectural fit, naming/module conventions consistent with the rest of the repo, no parallel implementations of existing utilities, layering respected, public surface kept small |
| **tests-coverage** | *"Assume someone refactors this next sprint without reading the tests. Will the tests catch the breakage?"* | Are new code paths tested? Are edge cases covered? Test quality (no over-mocking, deterministic, fast), missing regression tests for the bug being fixed, coverage of error paths |

The per-agent **Execution mandate** above IS the evidence bar (canonical: `skills/my-review/SKILL.md` ("The evidence bar")) — it reaches the sub-agents through their prompts; the consolidator itself only merges and never files unverified findings of its own.

## Collect — a lens has delivered only when its findings are in hand

Keep a ledger of the seven lenses and close it before consolidating. A lens is delivered when you hold
its findings text: the `Agent` tool result, or a message from that agent carrying the findings.

**Nothing else counts as delivery.** An idle notification, an availability event, a status line, a
message summary, or the agent simply having stopped are all signals *about* an agent, never its report.
Treating one as completion is how a swarm gets declared finished, or failed, while it is still working
— do not diagnose the run from these events at all.

When the ledger is short:

1. Re-request once, from that agent, naming the delivery channel and restating the output contract.
2. Still nothing after that single re-request: stop chasing. Record the lens as **NOT DELIVERED**.

Never synthesize a missing lens's findings, never infer them from another lens, and never let a
missing lens pass silently — it appears as `NOT DELIVERED` in the micro-summary, and the verdict cannot
be `ship` while coverage is incomplete. Say plainly which lenses are missing when presenting the report.

## Consolidate

Once the ledger is closed:

1. **Merge** findings into a single report grouped by severity (Critical → Low → Positive), each finding tagged with its source lens and complexity index, e.g. `[security] cx:S SQL string built via concatenation src/db.py:42` followed by its `→ **Fix (inst|class):**` line.
2. **Deduplicate** — if two lenses raised the same `file:line` with the same root cause, keep one entry and list both lens tags.
3. **Assign stable IDs** during consolidation (`C1, C2, … H1, H2, …`) so the user can reference findings in follow-up (`"apply C1 and H3"`). Subagents do **not** number their own findings — numbering is the consolidator's job after dedup.
4. **Question a lens rather than guess.** Every agent stays addressable by name after its report lands
   (`SendMessage` resumes it with its investigation intact). Send one back a question when two lenses
   contradict each other, when a Critical/High arrives without the evidence its mandate required, or
   when a fix's tier or cost is unclear. It answers from what it actually ran; you would be re-deriving
   it. Never publish a finding you do not believe — resolve it or drop it.
5. **Top of report**: 2-3 sentence executive summary + a one-line verdict (`ship`, `ship-with-followups`, `block`).
6. **Bottom of report**: per-lens micro-summary (one line each) so the user can see whether any lens came back clean, noisy, or `NOT DELIVERED`.
7. Use the format in [template.md](template.md).

## Report before acting (mandatory)

The deliverable of this skill is the **report**, and the turn ENDS with it — unless explicitly stated
otherwise (e.g. a fix or feature loop such as `iterative-review`, `implement-loop`, or `ship-feature`,
whose flow by design acts on findings):

- Show the full consolidated report to the user and **stop**. Do not edit files, apply fixes, or run any
  mutating command in the same turn — not even "trivial" or "quick win" findings.
- Fixes happen only after the user explicitly selects findings (e.g. *"apply C1 and H3"*, *"fix all
  Highs"*). A general "go ahead" earlier in the conversation does not pre-authorise acting on findings
  the user has not seen.
- When invoked from another skill or loop, the report is still surfaced in full before anything acts on
  it; the caller's own flow then decides what happens next.

## Fix scope — offer after the report

Once the consolidated report is printed **in full**, ask how far down the severity ladder to go — as a
plain-text numbered list, in the same message, so the choice is explicit and the report stays visible:

1. **Fix everything** — from the first Critical to the last Low.
2. **Critical + High + Medium** — leave Lows.
3. **Critical + High** — leave Medium and Low.
4. **AI-proposed scope** — you propose the explicit list of findings worth addressing (by ID), cutting
   across severities on judgement rather than a clean severity band. The user approves before you fix.
5. **Something else** — user names a subset (specific finding IDs, a single severity, or "none").

Drop any option that would be redundant or empty — when two would cover the exact same findings (e.g.
no Lows makes 1 and 2 identical), keep only one. If nothing actionable was found, skip the menu and say
so. The complexity index is useful here: a `cx:L` Medium may be worth deferring while a `cx:S` Low is
free, so option 4 should weigh cost against severity rather than following the band.

**When invoked from another skill or loop** (`iterative-review`, `ship-feature`, `implement-loop`, or
any caller whose flow acts on findings by design): print the full report, then **skip the menu and hand
back** — the caller owns the fix scope, and asking here stalls its loop.

Apply exactly the selected scope, nothing beyond it. Findings left out of scope stay in the printed
report as the record of what was consciously waived.

## Release the swarm

Keep the agents alive while their findings are still in play — you question a lens during
consolidation, the user challenges one, or a fix needs the reasoning behind it. A live agent answers
from its own investigation instead of you re-deriving it.

Once the findings are validated or challenged and the scope decision is made, the swarm has no further
use: release every agent with a `SendMessage` `shutdown_request`. Leaving seven agents idling costs
context and turns them into stale reviewers of a tree that has since changed under them.

Release earlier only when a lens is definitively done with — `NOT DELIVERED` after its single
re-request, or a report the user has already dismissed.

## Output discipline

- Never invent line numbers — if an agent returns a finding without `file:line`, drop it or ask that agent to re-run with locations.
- Don't flood with style nits when logic/security bugs exist — surface those first.
- If a lens returned nothing, write `None.` under it; do not pad.
- Cite the scope at the top of the report so the user can reproduce: base ref, head ref, changed-file count.
