---
name: babysit
description: Use when the user says "babysit", "babysit the PR", "babysit the deploy", "watch the CI", "monitor the PR", "monitor the deploy", "tell me when CI is done", "tell me when the deploy is done", or when CI, a pipeline, a release workflow, a rollout or a long job must be watched until it ends. Not for a one-shot status question (sitrep).
# ToolSearch: T3 tools are deferred and must be loaded before the first call.
allowed-tools: Bash, Agent, ToolSearch, mcp__t3-code__watch_pull_request, mcp__t3-code__unwatch_pull_request
version: "1.0.0"
---

# Babysit

## Contract

- The watcher runs on a cheap model (`model: "sonnet"` or `"haiku"`). One watcher per target.
- The watcher reports the raw outcome only:
  - target and final state
  - for a failure: failing job name, URL, last 30 log lines
  - it never fixes, retries, merges or concludes
- The main thread decides what happens next: fix, merge, escalate, or re-run a job that failed on infrastructure (lost runner, network). A failing test is fixed, never re-run until green.

## Mechanism

| Target | Watch with |
|---|---|
| GitHub PR, in T3 Code | main thread only, no watcher agent (a subagent cannot watch): `watch_pull_request`, then end the turn. T3 wakes you on checks, comments or conflicts, so a PR with no checks never wakes you: read `gh pr checks <n>` first. `unwatch_pull_request` when handing back |
| GitHub PR, elsewhere | `gh pr checks <n> --watch --fail-fast` |
| GitHub workflow run, release | `gh run watch <id> --exit-status` |
| GitLab MR, pipeline | `glab ci status --live` on the branch |
| k8s rollout | `kubectl rollout status deploy/<name> --timeout=10m`, then read the running image tag |
| anything else | Bash `run_in_background` with a `timeout`-bounded until-loop |

The watcher runs its command with Bash `run_in_background` and an explicit `timeout`: a foreground Bash call is cut at 10 minutes, shorter than most CI. When the timeout expires it reports `timeout` and the last state seen. Never poll from the main thread with short sleeps.

## Watcher prompt

```
Watch <target>: run `<command>` with Bash run_in_background and timeout <timeout>.
Do not fix, retry or comment.
When it ends or after <timeout>: report target, final state, and for a failure the
failing job name, its URL and the last 30 log lines.
```

## Notify

Notify the user with the appropriate means: their instructions first, else a notification tool if one is available. Only when they asked for it this time, once, on the final state.
