---
name: iterative-review
description: Iterate review + fix rounds on changed code until the tree is clean. Use before committing when changes are substantial or risky and a single pass isn't enough — when the user says "iterative review", "review until clean", "loop review and fix", or wants findings fixed and re-reviewed automatically. One of the accepted pre-commit reviews alongside /my-review and /swarm-review (prefer these when installed, otherwise an equivalent review skill), ahead of /smart-commit or an equivalent commit flow.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Skill, AskUserQuestion
version: "1.3.0"
---

## Task

Assess the current state with a review skill, fix the findings, re-assess, repeat until clean.

Default review skill: `/my-review`. If that is not available, fall back in order to `/review`, `/security-review`, or whatever review-style skill the user specifies.

**Language-agnostic.** Examples below are Go; substitute the project's toolchain (`pytest`, `cargo test`, `npm test`, `tflint`, `shellcheck`, …).

## Do not stop at the review

The review report is **input to step 2, not the deliverable** — printing findings and stopping is the
one failure this skill exists to prevent. Triage and fix in the same turn, without asking for
confirmation. The tell that you have slipped: you have printed the report and are reaching for the
end of the turn, or waiting for the user to react to findings. The only legitimate end-of-turn states:

1. An exit condition below is met (Empty / Iteration cap / Oscillation), or
2. The user interrupted with a course-correction, or
3. A gate failure needs a question to resolve (escalate explicitly — don't go silent).

## Loop

For each round (max 3):

1. **Assess** — invoke the review skill. Capture every finding, then keep going in the same turn: triage (step 2), display the table (step 3), fix (step 4).
2. **Triage** each finding into exactly one bucket:
   - **Fix** — real bug, test-provable defect, missing defense-in-depth on a security-relevant path (classify against OWASP Top 10 / OWASP API Security Top 10 and CWE where it applies), documentation out of sync with the code (README / ADR / help text / API reference / OpenAPI spec / example payloads that no longer match reality), or style violation that blocks the lint/test gate.
   - **Accept** — the finding is a trade-off whose cost is acceptable (e.g., a counter that does not persist across restarts). Record *why* in the triage table and the commit message; add a code comment only when it states a constraint the code cannot show.
   - **Escalate** — the finding touches a design decision or extends scope beyond the original change. Surface to the user; do not silently expand scope.
3. **Display the triage table, then proceed straight to Fix without waiting for approval:**

   | Finding | Bucket | Fix / Comment / Reason |
   |---|---|---|
   | ... | Fix / Accept / Escalate | ... |

   The table is informational — the user can follow along and interrupt; do not pause for confirmation. If they interject, adjust the table and continue.
4. **Fix** the items in the Fix bucket only. Keep diffs minimal. Do not refactor adjacent code.
5. **Gate** — before re-assessing, all of the following must pass on the changed code. The commands below are examples; pick the project's equivalent:
   - build — e.g., `go build ./...`, `cargo build`, `npm run build`, `python -m compileall`, `terraform validate`
   - static analysis — e.g., `go vet ./...`, `mypy`, `ruff check`, `tsc --noEmit`, `cargo clippy`
   - unit / integration tests — e.g., `go test ./...`, `pytest`, `cargo test`, `npm test`
   - concurrency / stress checks where the language supports them — e.g., `go test -race`, `pytest -p xdist`, `cargo test --release`
   - project lint gate — `pre-commit run --all-files` if `.pre-commit-config.yaml` exists; otherwise the repo's documented lint entrypoint (`make lint`, `npm run lint`, …)
   - doc-alignment check — spot-check that any README / spec / examples touched by the change still match the code (a stale curl example in README is a lint-equivalent gate failure).

   If any gate fails, stay in the Fix step and resolve before re-assessing.
6. **Re-assess with a fresh pair of eyes.** Do not anchor on the previous review — re-read the code, not the prior diff summary.

## Exit conditions

Stop when **any** of these holds:

- **Empty** — no Critical or High findings remain, the gate is green, and remaining Medium/Low findings are Accept items (trade-offs recorded in the triage table).
- **Iteration cap** — 3 rounds completed. Summarize remaining findings with triage buckets and hand back to the user with "escalation needed".
- **Oscillation detected** — see below.

## Oscillation defense

Reviewers in the same conversation can flip-flop a finding ("add X" → next round "remove X"). Guard against this:

- Keep a short mental log of what was changed each round (one line per fix).
- Before applying a re-fix, check the log: if the change would *reverse* a prior fix, the finding is a design disagreement between reviewer and implementer. **Stop the loop and surface it to the user**; do not oscillate.
- Avoid tunnel vision. Gain altitude when re-assessing — ask "does this finding make sense in the whole design?" not just "does the local code match the reviewer's taste?".

## Scope discipline

- Scope is the **whole feature** — `<merge-base>...HEAD` plus uncommitted work — not merely this round's diff, and not the whole repository.
- Pre-existing lint/test problems in files you did not touch: note them and skip, unless they block the green-gate. If they block, suppress via config (with a comment naming what the suppression covers) rather than expanding the diff.
- Do not introduce new features, refactors, or abstractions that were not flagged by the review.
- Documentation updates count as in-scope when the change alters behavior the doc describes. Out-of-scope doc drift (unrelated stale sections) should be noted to the user, not silently fixed.

## Commit policy

- **Do not commit between rounds** unless the user explicitly says so.
- Hand back a clean working tree with all staged/unstaged changes visible to the user for review.
- If a pre-commit hook suppression is added, flag it in the round summary so the user can audit.

## Round summary (delivered at end of each round, after Gate passes)

Closing recap with the same table shape as the pre-Fix display, plus the outcome of each Fix row (what landed) and the gate result:

| Finding | Bucket | Outcome |
|---|---|---|
| ... | Fix / Accept / Escalate | diff / comment / escalated note |

Plus the base ref the scope was resolved against, the gate result (green / which check failed) and a one-line note on whether oscillation was detected and how it was handled.

<!-- include: skills/my-review/SKILL.md#review-doctrine -->
## Scope on a feature branch — the diff is the entry point, not the boundary

On a feature branch the unit of review is the **feature**, not the diff in front of you: resolve the
base (`git merge-base <base> HEAD`, `<base>` = first existing of `origin/develop`, `origin/trunk`,
`origin/main`, `origin/master`), read `<base>...HEAD` plus uncommitted work as one unit, and cite the
base ref in the report.

- Defects an earlier commit of the branch introduced are in scope, even when today's diff does not
  touch them.
- Judge every fix against the whole feature: repairing the newest hunk while an earlier commit keeps
  the same broken shape is an `inst` fix where one feature-wide `class` fix exists.
- The feature is the boundary — unrelated pre-existing repo debt stays out.

## The evidence bar — reading is not verification

A Critical or High finding must carry **evidence you produced**, not an argument you constructed:

- The command you ran and the output you saw. `curl` it, `pytest` it, `docker build` it, `issubclass()`
  it, `psql` it.
- If the defect is in code that can be executed, **execute it**. Scaffold a throwaway project if that is
  what it takes; it costs minutes.
- **Break it on purpose**: delete the fix and confirm the test goes red; inject the drift and confirm the
  check fails. A guard nobody has bypassed is a guard nobody has tested.
- Cannot run it? Say `[unverified]` in the finding. That is honest and useful. Silently implying you ran
  it is neither.

Findings from reading alone are hypotheses. Ship them as hypotheses.

## The fix bar — do not propose decoration

Every fix you propose is one of three tiers. Name the tier.

| Tier | What it is | Verdict |
|---|---|---|
| **`deco` — decoration** | A promise: *"keep them in sync"*, *"remember to"*, *"document that"*, *"be careful"*, *"reviewers should check"* | **Never propose alone.** It is the bug wearing a hat |
| **`inst` — instance fix** | Repairs this occurrence | Acceptable when no `class` fix exists, or it costs more than the bug |
| **`class` — class fix** | Makes the defect **un-shippable**: a test that fails without it, a lint rule, a CI gate, a type, a schema, an invariant, a deleted duplicate | **Prefer this whenever it exists and is cheap** |

If you propose `inst` where a `class` fix exists, **say so explicitly and justify it** — name its cost and
why it is not worth paying today. Let the human overrule you. Quietly choosing the cheap path and
presenting it as the fix is the failure this bar exists to prevent.

**The tells of a `deco` masquerading as a fix**: it adds words to a document and changes no behaviour; it
relies on a future human remembering; it would not have caught the bug that just happened. Ask of every
fix: *"if this had been in place last week, would the defect have been impossible — or merely
discouraged?"*

## Comments: constraint, not justification

A comment that justifies a choice belongs in the commit message — that is where history is queried. A
comment in the file states a constraint a reader cannot derive from the code (`COPY *.py does NOT match
run-*.sh`, `chown before USER or the writable dir breaks`). Flag both directions: rationale parked in the
file, and an undocumented gotcha. Density is part of it — one line unless the constraint needs two; a
six-line comment wall over a two-line change is a finding, and so is a comment that paraphrases the
statement below it.
<!-- /include -->
