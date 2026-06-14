---
name: iterative-review
description: Iterate review + fix rounds on changed code until the tree is clean
version: "1.0.0"
---

## Task

Assess the current state with a review skill, fix the findings, re-assess, repeat until clean.

Default review skill: `/my-review`. If that is not available, fall back in order to `/review`, `/security-review`, or whatever review-style skill the user specifies.

**Language-agnostic.** This skill works on any project: Go, Python, TypeScript, Rust, Java, shell, Terraform, Kubernetes manifests, whatever. The examples below happen to be Go (`go build`, `go test -race`, …) because that is one common case — substitute the project's native toolchain (`pytest`, `cargo test`, `npm test`, `tflint`, `shellcheck`, `kubectl apply --dry-run`, …) as appropriate.

## Failure mode to avoid (read this first)

The default failure mode is: invoke the review sub-skill, render its findings to the user, **end the turn**. Do not do that. The review sub-skill's output is *intermediate raw material*, not the deliverable of this skill. You are running a multi-round loop; the review is step 1 of *N* steps, not the answer.

Symptoms that you've slipped into the failure mode:

- You posted the review template (Critical / High / Medium / Low / Positive sections) and stopped.
- You're "waiting for the user to react to the findings."
- You're thinking "the review is done, ball's in their court."

If any of those describe your current state, you are mid-skill, not done. **Continue to triage and fix in the same turn**, without asking for confirmation.

The only legitimate end-of-turn states are:
1. The exit conditions below have been met (Empty / Iteration cap / Oscillation), or
2. The user has interrupted you with a course-correction, or
3. A gate failure that needs a question to resolve (escalate explicitly — don't go silent).

## Loop

For each round (max 3):

1. **Assess** — invoke the review skill. Capture every finding. **Do not render the review verbatim and stop.** The review sub-skill returns a structured findings doc; that doc is your input to step 2, not your output to the user. Treat the sub-skill's return like the result of any other tool call — log mentally, then keep going. (You may quote findings inside the triage table in step 3, but only as part of the table.)
2. **Triage** each finding into exactly one bucket:
   - **Fix** — real bug, test-provable defect, missing defense-in-depth on a security-relevant path, documentation out of sync with the code (README / ADR / help text / API reference / OpenAPI spec / example payloads that no longer match reality), or style violation that blocks the lint/test gate.
   - **Accept with comment** — the finding is a trade-off whose cost is acceptable (e.g., a counter that does not persist across restarts). Leave a code comment capturing *why* it is acceptable.
   - **Escalate** — the finding touches a design decision or extends scope beyond the original change. Surface to the user; do not silently expand scope.
3. **Display the triage table, then proceed straight to Fix without waiting for approval:**

   | Finding | Bucket | Fix / Comment / Reason |
   |---|---|---|
   | ... | Fix / Accept / Escalate | ... |

   The table is informational so the user can follow along (and interrupt if they disagree); do not pause for confirmation. Move directly into the Fix step in the same turn. If the user interjects with a course-correction, adjust the table and continue.
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

- **Empty** — no Critical or High findings remain, the gate is green, and remaining Medium/Low findings are Accept-with-comment items (documented trade-offs).
- **Iteration cap** — 3 rounds completed. Summarize remaining findings with triage buckets and hand back to the user with "escalation needed".
- **Oscillation detected** — see below.

## Oscillation defense

Reviewers in the same conversation can flip-flop a finding ("add X" → next round "remove X"). Guard against this:

- Keep a short mental log of what was changed each round (one line per fix).
- Before applying a re-fix, check the log: if the change would *reverse* a prior fix, the finding is a design disagreement between reviewer and implementer. **Stop the loop and surface it to the user**; do not oscillate.
- Avoid tunnel vision. Gain altitude when re-assessing — ask "does this finding make sense in the whole design?" not just "does the local code match the reviewer's taste?".

## Scope discipline

- Scope is the **changed code** from the original task, not the whole repository.
- Pre-existing lint/test problems in files you did not touch: note them and skip, unless they block the green-gate. If they block, suppress via config (with a comment explaining why) rather than expanding the diff.
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

Plus the gate result (green / which check failed) and a one-line note on whether oscillation was detected and how it was handled.
