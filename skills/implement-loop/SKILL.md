---
name: implement-loop
description: >-
  Drive a multi-phase implementation autonomously from a handoff doc, plan, or ticket using a
  disciplined dev loop: dev → test + dual guards → review → address findings (edge cases, not happy
  path) → end-to-end coherence check → commit on the feature branch → repeat. Enforces measurable
  per-phase definition-of-done, stop-and-ask escalation on design forks, a human checkpoint at
  merge, and a living unaddressed-points list mirrored to the tracker. Use when the user says
  "implement loop", "run the loop", "work through the plan/handoff autonomously", or hands a
  handoff/plan/ticket and asks you to build it end-to-end.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, Skill, TaskCreate, TaskUpdate, TaskList, AskUserQuestion
version: "1.1.1"
---

# Implement from handoff — the autonomous build loop

Turn a handoff/plan/ticket into shipped, reviewed code without hand-holding — while staying safe:
escalate on design forks, human-gate the merge, never let findings rot.

## 0. Bootstrap (once, before the loop)

1. **Locate the source of truth** — a handoff doc, a plan, or a tracker ticket. If none was named
   and context is thin, **ask** for it; do not invent scope. Read it fully before touching code.
2. **Extract phases + per-phase definition-of-done (DoD).** Use the handoff's if present. If DoD is
   missing or vague, **derive candidates and confirm with the user** — "done" must be checkable (a
   test green, a metric moved, a command exits 0), never a vibe.
3. **Branch / worktree.** Create the feature branch off the stated base. One branch for the effort;
   per-slice commits land on it.
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
   Record the mode + worktree path on the tracking list so a resumed session finds it.
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

## 1. The loop (per phase, and per reviewable slice within a phase)

```
dev → test + guards → review → address → coherence → commit → repeat
```

### 1.1 Dev
Implement the smallest change that moves toward the phase DoD and can stand alone. Match surrounding
code style; comments explain WHY, not WHAT.

### 1.2 Test + DUAL guards (both, every iteration — not just one)
- Run the **test suite**, `pre-commit run --all-files` (if configured), and **coverage** — coverage
  must **not decrease** vs baseline (a floor, not decoration).
- **Structural / static guard** — the invariant the work must establish, checked statically:
  an import-graph or dependency assertion, a lint rule, a type check, an API-surface snapshot.
  Proves the *intended change* happened.
- **Behavioral / runtime guard** — run the thing for real end-to-end and assert observable output:
  a smoke run, an integration test, a request/response, a CLI invocation → expected exit + output.
  Static-clean but runtime-broken is the classic refactor trap; the structural guard alone does NOT
  catch it.
- Pre-commit outcomes: auto-fix (review + re-stage), project failure (fix root cause), hook broken
  upstream (stop and ask — never `--no-verify` / `SKIP=` without explicit per-turn authorization).

### 1.3 Review
Run a review pass with `my-review` (focused), `iterative-review` (converge fix rounds), or
`swarm-review` (broad / multi-angle). Feature work MUST pass a review before commit.

### 1.4 Address findings — PROPERLY, no shortcuts
- Fix the **root cause, not the symptom**. Cover the **details**, not just the headline.
- **Do not stop at the happy path.** Hunt edge cases relevant to the change: empty / null / missing
  inputs, absent env/config/credentials, partial or out-of-order results, boundary values,
  concurrency / cancellation / mid-operation failure, error and exception flows, lazy/conditional
  paths that only fire at runtime, resource cleanup on failure.
- A finding is **addressed** only when its edge cases are handled **or** explicitly **waived with
  reasoning**. Every waiver goes on the unaddressed-points list — never silent.

### 1.5 Coherence check (last gate before commit)
A deliberate end-to-end read of the slice's logic: does it actually do what it claims; are all edges
consistent; do the non-happy paths (errors, empties, missing deps) behave sanely; does it hold the
phase invariant. Distinct from review — review finds issues, coherence confirms the whole still
makes sense.

### 1.6 Commit (autonomous on the feature branch)
Commit via `smart-commit` (branch + Conventional Commit + gated push). Subject concise, body only for
non-obvious *why*. No AI/assistant attribution. Stage files explicitly by name (never stage-all).
Each commit leaves the tree green and the guards passing — so any commit is a safe rollback point.

### 1.7 Repeat
Next slice / next phase.

## 2. Definition of done (gate between phases)
Do not advance until the current phase's **measurable** DoD is met: structural guard satisfied,
behavioral guard passing, suite + coverage green. State the DoD check explicitly when closing a phase.

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

## 6. Composition
For a **wide** phase, the dev step can delegate the parallel build to a fan-out executor (e.g. a
wave-runner / parallel-agent skill), then run this loop's guards, review, and commit around the
result. This skill is the disciplined outer loop; a parallel executor is one primitive inside it.

## 7. Exit
The loop ends when all phases meet DoD, the unaddressed list is empty or every remaining item is a
recorded conscious waiver, both guards pass on the final state, and the MR is prepared for human
review. Report: phases done, final guard/coverage state, the unaddressed/waived list, and the MR link.
If an isolated worktree was used, leave it in place until the user confirms the merge, then propose
its removal (`git worktree remove <path>`) as a gated step — never auto-remove unmerged work.
