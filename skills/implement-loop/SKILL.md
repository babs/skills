---
name: implement-loop
description: >-
  Use when the user says "implement loop", "run the loop", "autonomously", "AFK", "without
  supervision", "take it from here", "do the whole thing", "build it all", "I'll check back later",
  or hands a handoff doc, plan, ticket, or spec and asks you to build it end-to-end on your own.
  Drives the multi-phase implementation through a disciplined autonomous dev-test-review-commit
  loop per phase, with a human checkpoint at merge. Mode not stated → ask one question, supervised
  (ship-feature) or autonomous (this skill); never default to either loop.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, SendMessage, Skill, TaskCreate, TaskUpdate, TaskList, AskUserQuestion
version: "1.8.0"
---

# Implement from handoff — the autonomous build loop

Turn a handoff/plan/ticket into shipped, reviewed code without hand-holding — while staying safe:
escalate on design forks, human-gate the merge, never let findings rot.

## 0. Bootstrap (once, before the loop)

1. **Locate the source of truth** — a handoff doc, a plan, a tracker ticket, or an approved spec. If none was named
   and context is thin, **ask** for it; do not invent scope. Read it fully before touching code.
2. **Extract phases + per-phase definition-of-done (DoD).** Use the handoff's if present. If DoD is
   missing or vague, **derive candidates and confirm with the user** — "done" must be checkable (a
   test green, a metric moved, a command exits 0), never a vibe.
   - Source with numbered acceptance criteria, `AC1`, `AC2`, … → extract them per phase too. Cite
     one as `<source id>-AC3`: `027-AC3` for spec 027, `PROJ-123-AC3` for a ticket, `ACME-027-AC3`
     when the spec header has an `**AC prefix**` line. Numbered ACs in a source with no id →
     agree an id in the §0.6 batch.
   - A source other than a spec-feature spec, with a numbered AC under no phase → assign it and
     confirm in the §0.6 batch.
   - A spec-feature spec with ACs not numbered, a phase without **Covers**, an AC not struck
     through under no **Covers**, or kept outside this repo with no `**AC prefix**` line → ask in
     the §0.6 batch: upgrade the spec, or run without AC tracking. Upgrade → once the branch
     exists, add what is missing, show it, wait for approval.
   - AC tracking is on when the ACs are numbered and the user did not decline it.
3. **Branch / worktree / dev mode.** Create the feature branch off the stated base. One branch for
   the effort; per-slice commits land on it.
   - **Isolated worktree (default when the user asks, or when the main checkout is dirty / in use):**
     create a dedicated `git worktree` so the loop never disturbs the user's working tree:
     `git worktree add -b <branch> <path> <base>` (put `<path>` outside the repo). **After creating
     it, operate exclusively from the worktree path** — every Read/Edit/Bash uses worktree paths.
     **Never `cd` back to the main checkout** (it shows a clean tree → false "work lost" alarm) and
     **never symlink the main `node_modules` then install through it**. Install deps fresh inside it.
   - **In-place branch** (no worktree) when the user did not ask for isolation and the checkout is
     clean and free.
   - **Unless the user explicitly stated "worktree" or "in-place"** (and the checkout state does not
     force a worktree), **ask which mode** as part of the front-loaded questions (§0.6) — do not
     silently default.
   - **Dev in a worker or inline.** Ask in the same batch unless the user stated it; suggest
     worker. Inline only when the user asks for it or the harness has no `Agent` tool. The review
     runs in a fresh agent either way (§1.3).
   Record the modes + worktree path on the tracking list so a resumed session finds them.
4. **Confirm standing authorization.** Autonomous commits on the feature branch need the user's
   explicit go for *this run* (it overrides the usual per-commit git gate). Ask once if not already
   granted. Pushing and **merging** are NOT covered — see §5.
5. **Open the tracking list** — a running list of unaddressed points (waived findings, deferred
   work, TODOs, open questions). Persist it in the tracker ticket if one exists, else a scratch file.
   Use `TaskCreate`/`TaskList` to mirror phases as tasks if helpful.
6. **Front-load the questions.** Read the whole source, scan every phase, and surface **all
   foreseeable open questions / design forks up front** — ask them now, in one batch, before coding.
   This maximizes autonomy afterwards: the loop then runs uninterrupted except at genuinely
   *crucial* forks that only emerge mid-build (§3). Ask at the **start** and at **crucial forks**,
   nowhere else — no drip-feed of routine questions. This governs *questions* only: the mandatory
   **safety stops are never skipped** — a broken upstream hook (§1.2) and the push/merge gate (§5)
   are not "questions" and still halt the loop for explicit authorization.
7. **Mark the spec.** A spec-feature spec → set `Status: in progress` as phase 1 starts. Spec kept
   outside this repo → edit it where it is, never commit it, and list every edit made to it in the
   §7 report.

## 1. The loop (per phase, and per reviewable slice within a phase)

```
dev → test + guards → review → address → coherence → commit → repeat
```

This context orchestrates: source, DoD, decisions, gate verdicts, git. Reading or writing the tree
at length runs in a subagent, dev per the §0.6 answer, so the loop's own context lasts the run.

### 1.1 Dev
Implement the smallest change that moves toward the phase DoD and can stand alone. Match surrounding
code style; comments explain WHY, not WHAT.

With the §0.6 answer *worker*, delegate the slice to a foreground `Agent` (general-purpose, no
`isolation`: a worktree fork edits a tree the gates here never run on). The source, the tracking
list, the DoD and every gate stay here; outside the spec, its index and the tracking files this
context edits nothing in the tree. The brief carries:
- the slice, its DoD and the ACs it covers;
- the tests to write: the slice's, plus the structural and behavioral guards (§1.2), spelled out;
  with AC tracking on, each AC test cites `<source id>-AC3`;
- the §0.6 answers it depends on;
- the absolute path of the tree to edit (the worktree, if any), used as an absolute path or
  `-C <tree>` on every command: a subagent's cwd resets between Bash calls;
- the applicable rules and conventions;
- the §3 fork list, inlined;
- no git state change of any kind;
- the exit contract, for this and every later message: `DONE` + files changed, or
  `BLOCKED: <fork>` + files touched so far, the fork left undecided.

Delivery = the `Agent` tool result or a message carrying `DONE` or `BLOCKED`, nothing else.
Backgrounding caveat: `skills/swarm-review/SKILL.md` ("Spawn the swarm"). Before each `Agent` call
or `SendMessage`, record `git -C <tree> rev-parse HEAD`, `branch --show-current`,
`status --porcelain -uall` and, per dirty path, the digest of `git -C <tree> diff HEAD -- <path>`
(`??` entries: `git -C <tree> hash-object <path>`); on every reply (return or `SendMessage`) compare
HEAD and branch, and take the changed files as the new `status --porcelain -uall` entries plus the
recorded paths whose digest moved, never from the worker's list. Drift → stop and surface: undoing
a git mutation needs the user's gate. A backgrounding acknowledgement is not a reply: wait for the
message. An empty set on `DONE`, or a final result without `DONE` or `BLOCKED` → resume it once via
`SendMessage` with that state; again → implement inline and say so.
`BLOCKED` → answer from the §0.6 record or the tracking list when already decided, else the user
per §3, the fork restated from this context's own read of the source; then resume the same worker
via `SendMessage` (only to the name the `Agent` call returned) and wait for its reply, the only
completion signal. Worker unreachable → a fresh worker, same brief plus
`git -C <tree> status --porcelain -uall` and "continue, do not restart". The worker's "tests pass"
is a claim: §1.2 re-runs every gate and sends any red one down the §1.4 route. Inline, by answer
or for lack of an `Agent` tool → implement here and say which.

### 1.2 Test + DUAL guards (both, every iteration — not just one)
- With AC tracking on, each test written for an AC cites it as `<source id>-AC3` in a comment or
  docstring.
- Run the **test suite**, `pre-commit run --all-files` (if configured), and **coverage** — coverage
  must **not decrease** vs baseline (a floor, not decoration).
- A `Dockerfile` in the tree makes the **image a gate**: `make docker-build` on every iteration that
  touches packaging, dependencies or files the Dockerfile copies, and once per phase regardless.
  Docker unavailable on this host → recorded as skipped, by name — never silently.
- **Structural / static guard** — the invariant the work must establish, checked statically:
  an import-graph or dependency assertion, a lint rule, a type check, an API-surface snapshot.
  Proves the *intended change* happened.
- **Behavioral / runtime guard** — run the thing for real end-to-end and assert observable output:
  a smoke run, an integration test, a request/response, a CLI invocation → expected exit + output.
  Static-clean but runtime-broken is the classic refactor trap; the structural guard alone does NOT
  catch it.
- Pre-commit outcomes: auto-fix (review + re-stage), project failure (fix root cause, worker mode
  via the §1.4 route), hook broken upstream (stop and ask — never `--no-verify` / `SKIP=` without
  explicit per-turn authorization).
- With the `Agent` tool, a foreground subagent runs these gates, given the tree's absolute path
  for `-C <tree>` on every command. It runs each gate once as given, fixes nothing, no `SKIP=`, no
  `--no-verify`, no git state change, and returns, per gate, the command, the exit code and the
  last 40 lines of output, all of it when the exit code is not 0. Delivery = the tool result or a
  message carrying those outputs, a backgrounding acknowledgement is not a reply. A result without
  per-gate output → resume it once via `SendMessage`, again → run the gates here and say so. The
  §1.1 snapshot and compare apply, and the changed set, usually empty, is the auto-fixes to review
  before one more gate run, auto-fixes again → hook broken upstream. The verdict is read here from
  that output, never from the subagent's summary.

### 1.3 Review
Run a review pass with `my-review` (focused) or `swarm-review` (broad / multi-angle). Feature work
MUST pass a review before commit. `swarm-review` dispatches its own reviewers; `my-review` runs as
below.

<!-- include: skills/iterative-review/SKILL.md#fresh-review -->
**Each review round runs in a fresh agent.** Spawn one foreground `Agent` (general-purpose, no
`isolation`: a `remote` fork uploads the tree, a `worktree` one reviews HEAD without the uncommitted
work) per round; never message an earlier reviewer. Prompt contract and backgrounding caveat:
`skills/swarm-review/SKILL.md` ("Spawn the swarm"); delivery = the `Agent` tool result or a
message carrying the report, nothing else. The prompt states:

- invoke the review skill this skill names via the Skill tool, on behalf of this skill: no
  fix-scope menu, no self-grade;
- the absolute path of the tree under review (the worktree, if any), used as an absolute path or
  `-C <tree>` on every command: a subagent's cwd resets between Bash calls; every command runs
  there except the auto-fixing gates below, and the `Reviewed-tree:` digest is stamped from that
  tree;
- the base ref, plus the spec, phase and AC ids when there are some;
- from round 2: the earlier fixes, to be verified while hunting for what they introduced, and the
  waivers (`Accept` items, in iterative-review) with their reasons, re-raised only on new evidence;
- edit nothing in that tree, auto-fixing gates (pre-commit, formatters) included: run them in a
  throwaway worktree;
- return the report verbatim, closed with the `Reviewed-tree:` line, stamped by the reviewer with
  the command from `skills/my-review/SKILL.md` ("Output") when the review skill
  did not.

On return, recompute the `Reviewed-tree:` line in the intended tree and require equality. A
mismatch, no report, or no `Reviewed-tree:` line → re-dispatch once with the path restated, never
triage; again → review inline and say so. Print the returned report in full, unmodified; the user
does not see agent output. The fix decision stays here. Three rounds per change under review at
most; a fix that would reverse an earlier round's fix is a design disagreement → stop and surface
it; cap reached → the including skill takes the remaining findings, fixed or waived per its own
rules. Sweep dead
reviewers' worktrees after each round, selection command in `skills/my-review/SKILL.md` ("The
evidence bar"). No `Agent` tool in this harness → review inline and say so.
<!-- /include -->

### 1.4 Address findings — PROPERLY, no shortcuts
- Fix the **root cause, not the symptom**. Cover the **details**, not just the headline.
- **Do not stop at the happy path.** Hunt edge cases relevant to the change: empty / null / missing
  inputs, absent env/config/credentials, partial or out-of-order results, boundary values,
  concurrency / cancellation / mid-operation failure, error and exception flows, lazy/conditional
  paths that only fire at runtime, resource cleanup on failure.
- Worker mode: fixes go via `SendMessage` to the worker that built the slice, under the §1.1
  contract; wait for its reply before §1.2. Slice built by fan-out (§6), or worker gone → a fresh
  worker with a §1.1 brief plus the findings.
- A finding is **addressed** only when its edge cases are handled **or** explicitly **waived with
  reasoning**. Every waiver goes on the unaddressed-points list — never silent.
- **Re-run 1.3 on the fixes** (same slice, same round cap) before 1.5 — a fix is
  unreviewed code, and 1.5 is a coherence read, not a review.

### 1.5 Coherence check (last gate before commit)
A deliberate end-to-end read of the slice's logic: does it actually do what it claims; are all edges
consistent; do the non-happy paths (errors, empties, missing deps) behave sanely; does it hold the
phase invariant. Distinct from review — review finds issues, coherence confirms the whole still
makes sense. Read the slice's changed set, every reply's since the slice began, with
`git -C <tree> diff HEAD -- <paths>` and `git -C <tree> diff --no-index /dev/null <path>` for `??`
paths, not the tree.

### 1.6 Commit (autonomous on the feature branch)
Commit via `smart-commit` (branch + Conventional Commit + gated push). Subject concise, body only for
non-obvious *why*. No AI/assistant attribution. Stage files explicitly by name (never stage-all).
Each commit leaves the tree green and the guards passing — so any commit is a safe rollback point.

### 1.7 Repeat
Next slice / next phase.

## 2. Definition of done (gate between phases)
Do not advance until the current phase's **measurable** DoD is met: structural guard satisfied,
behavioral guard passing, suite + coverage green. State the DoD check explicitly when closing a phase.
With AC tracking on, the phase also needs a test citing each AC it covers that is not struck through.
For each one run `grep -rE '(^|[^A-Za-z0-9_-])<source id>-AC3($|[^A-Za-z0-9_])'` on the test files.
Keep the pattern: `grep -w '027-AC3'` matches `ACME-027-AC3` too. No test citing it → back to 1.2,
never waived. Untestable → stop and ask, as in §3. List the phase's ACs in the phase-close note of
§4.
Self-grade the phase per the block below; the loop-wide grade at §7 is a separate one.

## 3. Escalation — stop and ASK, do not guess
Pause and ask the user at a genuine **design fork**, not for routine choices:
- a public signature / interface / schema change;
- a runtime-behavior change visible to other components or users;
- an architectural choice the handoff left open (a boundary, an injection shape, a data model);
- a guard breaking in a way that implies a contract change;
- ambiguity where two readings of the handoff diverge materially.
Guessing at a fork costs more churn than a one-line question. Routine reversible choices: decide,
note it, move on.

## 4. Tracking (mandatory, across the whole loop)
- Maintain the **unaddressed-points list** continuously; **mirror it onto the tracker ticket** so
  state survives a dead session.
- **Re-evaluate the list every iteration** — recheck whether deferred items are now unblocked or
  newly relevant; pull them in when they are.
- **Surface the list at every phase boundary.** Nothing rots silently. Push a short progress note to
  the tracker at each phase close.

## 5. Human checkpoint (the one thing that is never autonomous)
Per-slice commits on the feature branch are autonomous. **Pushing** and **merging** (opening/merging
the MR/PR) are a **human review gate** — machine self-review is signal, not merge authority. Prepare
the MR per repo conventions, then hand off the merge decision to the user. Propose any git mutation
beyond branch-local commits (push, force-push, tag, merge) and wait for explicit approval.

## 5b. Related skills

This is the **autonomous** loop, driven from a handoff doc, plan, ticket, or approved spec. The split
with **`ship-feature`** is pacing, not the artifact: unattended execution → this loop; a build the user
watches phase by phase, with a review gate they attend — typically a `specs/NNN-slug.md` from
`spec-feature` — → `ship-feature`. Same discipline, tighter human leash.

## 6. Composition
For a **wide** phase, the §1.1 worker is replaced by a fan-out executor (e.g. a wave-runner /
parallel-agent skill); this loop's guards, review, and commit still run around the result. This
skill is the disciplined outer loop; a parallel executor is one primitive inside it.

Fan-out without an executor skill, in worker mode: one message, one §1.1 `Agent` per slice, same
tree.
- Only when the phase holds at least three slices with disjoint paths. Each brief lists the paths
  its worker owns, test files included, forbids every other path, and runs only those tests, the
  guards waiting for the §1.2 pass.
- Same tree, no worktree per worker. Merging them back brings conflicts and nothing else.
- No gate while a worker runs. Once every worker has returned `DONE`, one §1.2 pass over the
  union, then §1.3 over the union as one change under review.
- The changed set is read once, after the last `DONE`, as in §1.1. A path in it outside every
  declared set → stop and surface, as for git drift.
- Phases never run in parallel. Phase N+1 starts on phase N's DoD.

## 7. Exit
The loop ends when all phases meet DoD, the unaddressed list is empty or every remaining item is a
recorded conscious waiver, both guards pass on the final state, and the MR is prepared for human
review. Report: phases done, final guard/coverage state, the unaddressed/waived list, and the MR link.
With AC tracking on, list each AC not struck through with the test that cites it. A spec-feature
spec → tick the ACs not struck through, set `Status: shipped`, update `specs/README.md`, and commit
them before preparing the MR.
If an isolated worktree was used, leave it in place until the user confirms the merge, then propose
its removal (`git worktree remove <path>`) as a gated step — never auto-remove unmerged work.

Close the report with the self-grade below, covering the whole loop rather than the final phase.

<!-- include: skills/my-review/SKILL.md#self-grade -->
## Self-grade — close the cycle with two letters

Grade only once fixes have landed, and only for the cycle you own — invoked by another skill, hand
your inputs back ungraded and let the caller grade. Two axes, never collapsed into one letter:

- **Result** — the artifact: what is provably closed, what stays open. Cite the gate output, not an
  impression.
- **Process** — the record that produced it. Anchor it in the table; `+`/`-` nuance a band, they
  never round up into the next one.

| Letter | Process anchor |
|---|---|
| **A** | no round introduced a defect; what shipped was right when it was written |
| **B** | a gate, a lens or the user caught once what care missed |
| **C** | several rescue rounds — the fixes were the least reliable code in the branch |
| **D** | a guard written here validated nothing, or unverified work was presented as verified |
| **F** | the defect reached production or the user, and they are the ones who found it |

A defect a fix introduced counts against the process letter.

**One mandatory line: what the machinery caught that I did not** — the finding and its catcher (a
lens, a re-run, a question the user asked). `Nothing` is valid only when no round produced a new
defect.

Grade the record, not the last diff.
<!-- /include -->
