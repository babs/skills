---
name: ship-feature
description: >-
  Implement an approved spec phase by phase with the full quality loop — implement → write tests → run
  tests → my-review → fix ALL findings → re-review until clean → swarm-review for large features →
  tests + coverage → smart-commit. Use when the user says "implement the spec", "build feature NNN",
  "ship it", or asks to implement work that has a file in specs/. This is the human-paced loop; for
  fully autonomous multi-phase builds from a handoff doc, use implement-loop instead.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Skill, AskUserQuestion
version: "1.2.1"
---

# Ship a feature — the quality loop

Code that compiles is not the deliverable. Code that is specified, tested, reviewed, has every finding
addressed, and is committed with an honest message — that is the deliverable.

The loop, per phase of the spec:

```
implement → tests → run tests → my-review → fix ALL → my-review (clean?) → [swarm-review] → tests + coverage → smart-commit
```

## 0. Before touching code

1. **Read the spec** (`specs/NNN-*.md`). No spec → run `spec-feature` first. Do not implement from a
   chat message; that is how you build the wrong thing very efficiently.
2. **Refuse a spec with open questions.** Status must be `approved` and the Open questions list empty.
   If it is not, surface it and stop.
3. **Read the code you are about to change**, plus `AGENTS.md` and the applicable rules. Match the
   surrounding style — a feature that reads like a foreign body is a review finding on its own.
4. **Branch.** Feature work never lands on the default branch directly.

5. **Set `Status: in progress`** on the spec as you start phase 1 — a half-built spec that still reads
   `approved` is indistinguishable from one nobody has touched.

Work **one phase at a time**. A phase ends green and committed before the next one starts, so every
commit is a safe rollback point.

## 1. Implement

If the phase declares a **Data model impact** other than "None", schema change and model change ship
together, migration first — with whatever migration tooling the project uses (in projects scaffolded
here: `uv run ./db_migrate.py --create "..."` → write the SQL by hand → update `models.py` to match).
Both, always: a fast test layer that builds its schema from the models stays green with a missing
migration, which then only explodes at the e2e layer — or in production.

The smallest change that satisfies the phase and can stand alone. Follow the spec — if reality
contradicts it (the spec asks for something impossible, or a better design becomes obvious), **stop and
say so**. Update the spec, get it re-approved, then continue. Silently deviating from the spec destroys
the only contract you have.

Comments explain **why**, never what.

## 2. Write the tests

Tests come from the **acceptance criteria** — each one becomes at least one test. Then go past them:

- The happy path (one test, quickly written, weakly informative).
- **The edges — this is where the value is**: empty input, missing/null fields, no permission, no
  results, boundary values, duplicate submissions, the dependency being down, concurrent access.
- The error paths: assert the status code *and* the body shape, not just "it didn't crash".

A test that cannot fail is not a test. If deleting the implementation still leaves it green, it is
decoration — rewrite it.

## 3. Run them

```bash
make test          # or: pytest / pnpm test — whatever the project defines
pre-commit run --all-files
```

Everything green before review. A review of broken code wastes the review.

**Every gate the project defines must be run, and must pass.** If a test command is declared, it runs. If
a pre-commit config exists, it runs. Neither is conditional on your judgement of the change's size or
risk — that judgement is exactly what is wrong when a gate would have caught you. If the project declares
*no* test command or *no* lint gate, say so explicitly in your report: an unstated absence is
indistinguishable from a skip.

**Judge on the output, not the exit status** — an aggregate target can exit 0 over an inner failure;
when they disagree, the report wins and the gate itself is a defect to fix (details: smart-commit step 4).

Pre-commit outcomes: auto-fixed files → re-read and re-stage. Real failure → fix the root cause. Hook
broken upstream → stop and ask. **Never** `--no-verify` or `SKIP=` without explicit per-turn permission
from the user.

## 4. Review — `my-review`

Run `my-review` on the change.

## 5. Fix ALL findings — no exceptions

Every finding gets one of exactly two outcomes:

- **Fixed** — at the root cause, with the edge cases it implies, not just the line the reviewer pointed at.
- **Waived** — explicitly, in writing, with the reason, surfaced to the user. Never silently.

"I'll do it later" is not an outcome. A finding you skip is a finding you ship.

**A fix ships with the test that fails without it.** Write the fix, then *delete it* and watch the test
go red. If it stays green, you have written decoration and the bug will come back.

**Fix the class, not the instance, when you can.** Reviews grade fixes T0/T1/T2 (T0 = a promise, "keep
these in sync"; T1 = repairs this occurrence; T2 = makes the defect *un-shippable* — a test, a lint
rule, a CI gate, a type, a deleted duplicate). A T0 is not a fix; it is the bug with better manners.
Prefer the T2. If you settle for the T1, say so out loud and name what the T2 would have cost.

## 6. Review again — `my-review`

Re-run it on the fixed tree. Fixes introduce their own bugs; a fix that was never reviewed is
unreviewed code. Repeat 5 → 6 until a review comes back clean. (`iterative-review` automates this
converge-until-clean cycle if the rounds are piling up.)

## 7. Large feature → `swarm-review`

If the feature is large — touches multiple layers (DB + API + UI), changes auth/permissions, handles
money or personal data, or is simply big — run `swarm-review` for the multi-angle pass (security,
resiliency, tests, coherence, docs). Then **go back to step 5**: every finding gets fixed or waived.

**Always** swarm-review — regardless of size — when the change touches any of: a migration, the DB
engine/session wiring or pool/timeout settings, a health/readiness probe, graceful-shutdown/lifespan
wiring, an outbound HTTP call, authentication, or **personal data**. These are the
changes whose failure mode is an outage rather than a bug, and they are usually small enough to feel
safe.

Rule of thumb otherwise: if you hesitate about whether it is large, it is large.

## 8. Tests + coverage

```bash
make test          # fast layer — must be green
make test-e2e      # real database — before the merge request, not after (where the target exists)
make coverage      # enforced floors: backend --cov-fail-under, frontend vitest thresholds
```

(Targets per the project's own Makefile — run what it defines; a missing gate is reported, not skipped.)

Coverage is a **floor, not a target**, and the floor is a **ratchet**: `make coverage` fails below it,
and when coverage sits comfortably above it you **raise the floor in the same commit**. That is what
turns "coverage must not decrease" into a mechanical fact instead of a promise nobody can check — an
unenforced number is a decoration.

Never lower a floor to turn a red build green. New code arrives with its tests. Gaming the number
(asserting nothing, testing getters) is worse than a low number, because it lies.

The phase's **DoD from the spec** is now checked explicitly — state it, and say whether it is met. Not
met → back to step 1.

## 9. Commit — `smart-commit`

Run `smart-commit` (branch + Conventional Commit + gated push). Stage files by name; never stage-all.
No AI/assistant attribution anywhere in the message.

## 10. Next phase, then close

Repeat for each phase. When all phases are done:

- Tick the acceptance criteria in the spec, set `Status: shipped`, update `specs/README.md`.
- Update `docs/` if the architecture or data model actually changed.
- Prepare the MR/PR. **Merging is the human's call** — machine self-review is signal, not merge
  authority. Propose the push/MR and wait for the go-ahead.

## Output

Report per phase: what was built, tests added, review rounds and what they found, the coverage delta,
the DoD verdict, and the commit. List every waived finding explicitly — the user decides whether a
waiver is acceptable, not you.
