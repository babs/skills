---
name: shall-settle
description: Settle a T3 Code thread once nothing is left waiting on an agent, a watcher or the user. Use when the user says "shall-settle", "settle the thread", "can we settle?", "put this thread away if it's done", or asks whether a T3 thread still waits on anything.
# ToolSearch: T3 tools are deferred and must be loaded before the first call.
allowed-tools: Bash, ToolSearch, CronList, mcp__t3-code__t3_pending_request, mcp__t3-code__t3_thread_list, mcp__t3-code__t3_thread_read, mcp__t3-code__list_scheduled_tasks, mcp__t3-code__unwatch_pull_request, mcp__t3-code__t3_thread_organize, mcp__t3-code__t3_thread_update
version: "1.2.0"
---

# Shall settle

Settle only on proof that nothing waits. One open item keeps the thread active. Settling is reversible (`unsettle`), so the user's invocation is the go: no extra confirmation.

## Scope

- T3 only. If either `mcp__t3-code__t3_thread_organize` or `mcp__t3-code__t3_thread_update` does not load (one ToolSearch `select:` for both), say this is not a T3 session and stop.
- Target: this thread by default; its id is `currentThreadId` from `t3_thread_list`. Given a thread id or link, read that thread with `t3_thread_read` (`view: "activity"`, small `limit`, `afterPosition` near its `itemCount`, so the latest items come back) instead of relying on memory.
- Another thread: delegated tasks, background commands and session crons belong to its own session and no tool lists them from here. Read them from its activity; an item the activity cannot show is `open: unverified`. Pass its `threadId` to every T3 call that acts on it (`t3_thread_update`, `unwatch_pull_request`, `t3_thread_organize`); omitted, they act on this thread.

## Clear the marker

First step, before any check. The attention marker is `⁉️` (U+2049, with or without U+FE0F). The title is `thread.title` from `t3_thread_read` on the target. If it starts with the marker, strip markers and spaces from its start until it begins with neither, then `t3_thread_update action:rename` with the result. If nothing is left, skip the rename; Decide handles it. A marker elsewhere in the title is user content: leave it.

## Check

Live checks only, run in parallel. Every item is `clear` or `open: <reason>`.

| Waits on | Check | Open when |
|---|---|---|
| User | `t3_pending_request action:list` (questions); `pendingRequestCount` from `t3_thread_read`; last messages of the thread | a pending question or approval; a question or option menu the user never answered (no answer is not a yes); a user request not done yet |
| Agent | each task delegated from the thread and its completion notification; no `task_status` (it marks results delivered) | no completion notification yet; a result never relayed to the thread |
| Background | background commands and `Monitor` watches started in the thread, with their completion notices; a `t3_background_wait` the thread's history shows set and never cleared | no completion notice yet, or output nobody read |
| Watch | `pullRequests` from `t3_thread_read`, then `gh pr view` / `glab mr view` | a linked PR/MR open and still part of the task (CI to wait on, merge pending) |
| Schedule | `list_scheduled_tasks`, `CronList`, a wakeup scheduled in the thread | a run tied to this thread still due |
| Promise | the assistant's last reply in the thread | a wait or a next step announced and not done ("waiting for…", "I'll come back when…", in any language) |
| Tree | in the thread's worktree: `git status -sb`, `git log --oneline @{u}..` | uncommitted or unpushed work the task meant to ship |

- A PR merged or closed, a task cancelled, or a watcher whose result was already reported is `clear`.
- A finished child's result counts as read only if it reached the thread (it was relayed).
- A leftover that the user explicitly waived is `clear`. Name the waiver.

## Decide

- Everything `clear`: `unwatch_pull_request` on each PR linked to the thread (its result says whether it was watched), then `t3_thread_organize action:settle` (settle applies at turn end, and a failed turn or queued message keeps the thread active). A title that was only markers gets `t3_thread_update action:regenerate_title`.
- Anything `open`: do not settle. Re-read `thread.title` (it may have changed during the checks), strip it the same way, and rename the thread to `⁉️ <cleaned title>`, or `⁉️` if the cleaned title is empty (`t3_thread_update action:rename`). Do not start, retry or fix anything to make it clear. Beyond the marker, this skill only judges.

## Output

Reply with this Markdown only, settled or not: no code fence, no prose around it, all of it in the user's language. One bullet per open item, all of them: the item and what clears it, a fragment, no rationale ("merge `feat/x` → your go", not "I'm waiting for your go to merge…"). A waiver, or the command that showed an item when it is not obvious, goes in parentheses on the line it supports. Keep the blank lines: without them Markdown folds the lines together.

Settled:

```markdown
Settled: <thread> · marker <m>

Clear 7 checks: user, agents, background, watches, schedules, promises, tree
```

Not settled (`Clear` line omitted when no check is clear):

```markdown
Not settled: <thread> · marker set

- **<waits on>**: <item> → <what clears it>
- **<waits on>**: <item> → <what clears it>

Clear <n> checks: <the clear ones>
```

`<m>`: `cleared` after removing a marker (`cleared, title regenerating` after `regenerate_title`, which is async), `unchanged` otherwise.

Every line comes from a check made in this run.
