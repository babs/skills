---
name: council-review
description: Use when the user says "council", "council review", "quorum review", "cross-provider review", "review with Sol", "review with Codex", or `/council-review`, or wants a change reviewed by another model family before commit.
# ToolSearch: T3 tools are deferred and must be loaded before the first call.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent, AskUserQuestion, ToolSearch, mcp__t3-code__orchestrator_capabilities, mcp__t3-code__delegate_task, mcp__t3-code__task_cancel, mcp__t3-code__task_status, TaskStop
version: "1.0.0"
---

# Council review

Each round, Claude Opus and GPT Sol review the same tree in parallel. You consolidate, fix, gate,
and dispatch a fresh round until both approve.

## Members

| Seat | Default | Effort |
|---|---|---|
| Claude | latest Claude Opus | `high` |
| Codex | latest GPT Sol | `high` (never `ultra`: it delegates) |

- Members the user names win over the defaults.
- Resolve ids every run: `orchestrator_capabilities` in T3, `codex debug models | jq -r '.models[].slug'`
  elsewhere. Never hardcode one.
- A seat you cannot reach is a blocker. Report it and stop. Never substitute a model or run with one
  seat: a council of one is a `my-review`.

## 1. Before round 1

1. Resolve the scope and base per `skills/my-review/SKILL.md` ("Scope on a feature branch"). Empty
   diff: stop and say so.
2. Fix what is already known (open PR comments, failing checks) before the council sees the tree.
3. Run the project gate (build, lint, tests, `pre-commit run --all-files` if configured). Note
   pre-existing failures, replayed on the base. The results go in the brief so members do not rerun
   the full suite against shared resources.
4. Write intent and out-of-scope in 1-2 sentences.
5. Resolve `<method>` = absolute path of `../my-review/` from this skill's base directory, never the
   tree under review. `test -r <method>/SKILL.md && test -r <method>/template.md`, else stop and report.
6. `<scratch>` = `$(git -C <tree> rev-parse --absolute-git-dir)/council-review`: one per worktree,
   and files there never move the `Reviewed-tree:` digest.

## 2. Dispatch a round

One message, two calls, in parallel.

**T3** (`orchestrator_capabilities` lists both providers): one `delegate_task` per seat with
`role: "review"`, `mode: "async"`, `isolation: "shared"` (a `worktree` child sees `HEAD` without the
uncommitted work), `target.providerInstanceId`, `target.model`, effort in `target.options` under the
option id that model lists (`reasoningEffort` for Codex, `effort` for Claude), and a new
`clientRequestId` per seat per round. Keep each `taskId`. Never `t3_thread_send` a review.

**Elsewhere**: Claude seat via `Agent` (`general-purpose`, `model: "opus"`, no `isolation`). Codex
seat in the background, PID recorded:

```bash
codex exec -m <sol-id> -c model_reasoning_effort=high -s read-only -C "<tree>" \
  -o "<scratch>/sol-r<N>.md" - < "<scratch>/brief-r<N>.md"
```

The brief goes through a file: a quoted argument lets the shell expand `$` and backticks in it. A
read-only sandbox blocks throwaway worktrees, so tell Sol to label findings it could not execute
`[unverified]`.

Wait for the completion notices. Do not poll, and do not edit the tree while a round runs.

### Brief (children get no history)

```
Council review, seat <Claude|Codex>, round <N>. Review only: do not edit this tree, commit, push,
comment on PRs, or start subagents.
Tree: <abs path>. Base: <sha>. Intent: <intent>. Out of scope: <scope>.
Gate results: <commands + pass/fail, pre-existing failures named>.
Diff: git -C <tree> diff <base>; git -C <tree> status --short (read untracked files too).
Method: read <method>/SKILL.md and follow its Task, doctrine and Output
sections, report format from <method>/template.md. Skip its fix-scope menu and
self-grade. Break things only in a throwaway worktree named review-wt-<sha>-<seat>-<pid>.
Exclusive resources (database, fixed port, fixture server): <Claude seat: you hold the token |
Codex seat: do not run, label the finding [unverified]>.
Hold to the smallest change; flag code, tests or guards the intent does not need.
Close with:
SCORE: <0-10>/10
VERDICT: APPROVE | CHANGES
Reviewed-tree: <line stamped per my-review "Output">
```

From round 2, append: the ledger (`fixed:` / `disputed:` / `accepted:` with evidence), the diff since
the last round, and "verify the fixes hold and hunt for what they introduced; mark each old id
`resolved` or `still open: <reason>`; re-raise waivers only on new evidence".

## 3. Collect

A seat has delivered when you hold its report text. A status line or an idle event is not a report.
A T3 completion notice without the report text: fetch it once with `task_status`.
On a missing report, error or timeout: stop the seat (`task_cancel` in T3; elsewhere `TaskStop` the
`Agent`, kill the Codex PID, an empty `-o` file is no report) and re-dispatch it once. Still
nothing: the seat is `NOT DELIVERED`, the round cannot approve, and you stop and report.

Recompute `Reviewed-tree:` in the tree and require equality with each report. Mismatch: re-dispatch
once.

## 4. Consolidate and triage

Print both reports in full (the user does not see child output), then one merged table:

| ID | Sev | Seats | Finding | Bucket | Fix / reason |
|---|---|---|---|---|---|
| H1 | High | both | `file:line` claim | Fix | `class`: test that fails without it |

- Dedupe on `file:line` + root cause. `Seats` = `both`, `Claude` or `Codex`.
- Check every finding yourself. A finding raised by both seats is not proof; a single-seat finding is
  not noise.
- Buckets as `skills/iterative-review/SKILL.md` ("Loop") step 2: **Fix**, **Accept** (owned trade-off,
  reason recorded), **Escalate** (design or scope change, goes to the user).
- When seats contradict each other, put both claims and your evidence in the row. Do not average.

Proceed to fixes without waiting for approval, as in `iterative-review`.

## 5. Fix and gate

- Smallest fix per Fix row, tier per `skills/my-review/SKILL.md` ("The fix bar"). Prefer delete or
  narrow over a new helper, lock, cache or option.
- Disagree with evidence (`file:line`, test, output). Do not agree to end the loop.
- Re-run the gate. Compare `git diff --shortstat <base>` with the pre-review figure: if the review grew
  the diff, cut first.
- A fix that reverses an earlier round's fix is a design disagreement: stop and surface it.

## 6. Next round or stop

Budget: 3 rounds. Up to 5 only for security, auth, permissions, data loss or concurrency while a
Critical/High with evidence stays open, or when the user asks.

| State | Action |
|---|---|
| Both `APPROVE` on the current digest, no Escalate open, gate green | **Agreed.** Stop. |
| No fix since the last round, no Critical/High open, every open finding Accepted, gate green | **Agreed, waivers recorded.** Stop. |
| An Escalate finding open, an item disputed after two replies, or budget spent | **Stuck.** Show both sides in 2-3 lines each; the user decides. Budget end is not approval. |
| Any fix since the last round, or a finding disputed | Next round, fresh dispatch for both seats. |
| Any other state | **Stuck**, handled as above. |

First matching row wins.

Do not commit or push between rounds.

## 7. Report

At exit, print:

```markdown
## Council review

Rounds: <N>. Outcome: agreed | agreed, waivers recorded | stuck | blocked

| Member | Round 1 | Round 2 |
| --- | --- | --- |
| Claude Opus <ver> (<effort>) | 7/10 | 9/10 |
| GPT Sol <ver> (<effort>) | 8/10 | 10/10 |
```

- A seat that gave no score: `no score`. Never invent one. Effort only when it was set and verified.
- Then: fixed / accepted / escalated findings with reasons, diff size before and after, gate result.
- If a PR/MR is open and the user asked to update it, put this section in its description. Edit the
  description, never post a comment.

Stamp only an `agreed` exit (waivers or not) whose digest equals the last round's. Any other exit
prints no `Reviewed-tree:` line: what changed after the last round is unreviewed.

<!-- include: skills/my-review/SKILL.md#reviewed-tree -->
**Stamp what was reviewed.** End the report with the digest of the exact tree the findings describe:

```bash
echo "Reviewed-tree: $(git rev-parse --short HEAD):$( { git diff HEAD; git ls-files --others --exclude-standard -z | while IFS= read -rd '' f; do git diff --no-index /dev/null "$f"; done; } | git hash-object --stdin | cut -c1-12)"
```

Untracked files are folded in deliberately: `git diff HEAD` alone does not see them, so a new module
or a new test added after the review would leave the digest unchanged and pass the gate unreviewed —
and new files are most of what a feature adds.

Print the line verbatim. `smart-commit` recomputes it before committing, so a review followed by more
edits stops being mistakable for a review of what ships. Re-emit it after applying a fix scope: the
tree moved, so the old digest is stale by construction.
<!-- /include -->

The self-grade closes the loop at exit, not per round. "What the machinery caught" names the seat.

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
