---
name: sitrep
description: Live status of the current work, and in T3 Code of every thread of the project. Use when the user asks "status?", "where are we?", "what's left?", "is it pushed?", "anything for me?", "are we done?", "what do you need from me?", "task status", "thread status", "what's running?", or comes back after being away.
# ToolSearch: T3 tools are deferred and must be loaded before the first call.
allowed-tools: Bash, ToolSearch, mcp__t3-code__t3_thread_list, mcp__t3-code__t3_thread_read
version: "1.0.0"
---

# Sitrep

A sitrep answers a question. It never starts, retries, fixes, sends to or settles anything, and never marks a delegated result delivered.

## Scope

- **This thread**: always.
- **T3 threads of the project**: when `mcp__t3-code__t3_thread_list` loads (ToolSearch `select:` once) and either this thread coordinates other threads or delegates, or the user asks about tasks or threads. This thread's project by default (omit `projectId`); all projects only when the user asks (`allProjects: true`).

## Gather

Check live and in parallel. Skip sources that do not apply.

- **Conversation**: what the user asked, what you promised, and questions put to the user that got no answer. An unanswered question is still open.
- **Background work**: subagents, background commands and T3 delegated tasks, each with its last completion notification. No notification yet means still running. No `task_status`: it marks results delivered.
- **Git**:
  - `git status -sb`
  - unpushed commits: `git log --oneline @{u}..`
  - `git worktree list`
- **Forge**: the branch's PR/MR and its checks (`gh pr view --json state,statusCheckRollup,url` or `glab mr view`), the linked issues' state, and open PRs no thread links (`gh pr list --state open`).
- **Deploy**, when the work ships: the version running vs the version released, read live.

### T3 threads

1. `t3_thread_list`, `limit: 50`, `includeSubagents: false`. Drop delegated children (a `parentThreadId` is set) and this thread (`currentThreadId`). Keep threads not `settled`, plus those updated in the last 24 h.
2. Per kept thread, `t3_thread_read` with `limit: 3`, `maxCharsPerItem: 1500`, `runLimit: 1`, `afterPosition` near `itemCount`. Read `status`, `activeRunId`, `pendingRequestCount`, `branch`, `pullRequests`, and the last assistant message: what it did, what it waits on, any question to the user. Never read a thread with a `parentThreadId`: reading a child's final result marks it delivered.
3. Classify each thread:

| State | When |
|---|---|
| In progress | `activeRunId` set, or a delegated task with no completion notification |
| Needs you | `pendingRequestCount > 0`, or an unanswered question or gate in its last message, whatever its `status` says |
| Blocked | its last message names a blocker (red CI, refused command, missing access) |
| Waiting | on CI, a deploy or another thread, nothing to do from the user |
| Done | its PR merged and seen live, or its deliverable handed over, nothing open |

## Output

In the user's language. This thread alone: 15 lines at most. With T3 threads: 25 lines at most.

```
Done          item, proof (URL, commit, version seen)
In progress   item, who runs it, next check
Waiting       item, on what (CI, deploy, another thread)
Blocked       item, blocker, what unblocks it
Needs you     1. question: one line of context, options with pro/con, my pick, confidence
```

With T3 threads, one line per thread under the same labels, naming the thread by its `link` verbatim, then:

```
Repo          default branch head, live version, open PRs, leftover worktrees
Watch out     a thread redoing work done elsewhere, two threads on one branch, a promise idle for hours
```

- An empty section says so in one word.
- Every state comes from a check made now. A thread not read this run is not reported.
- After an earlier sitrep in this conversation, mark what changed since it; still list every open item.
