---
name: handoff
description: Use when the user says "do a handoff", "make me a handoff", "continue in a new thread", "the rest happens in a new thread", "open another thread for X", "prepare a dedicated thread for X", or when context runs long and the work must continue in another session. Not for a prompt that already hands you a handoff doc to continue or build from, nor child work whose result comes back to this thread.
argument-hint: "What will the next session be used for?"
# ToolSearch: T3 tools are deferred and must be loaded before the first call.
allowed-tools: Read, Write, Bash, ToolSearch, mcp__t3-code__t3_thread_launch, mcp__t3-code__delegate_task
version: "1.0.0"
---

<!-- Adapted from mattpocock/skills `handoff`, MIT: see LICENSE next to this file. -->

# Handoff

## Write the document

Save it to the project's scratchpad (`.claude/scratchpad/` or `.scratchpad/`, gitignored), never to the OS temp directory. Name it `handoff-<slug>.md`.

Include:
- goal and current state: done, in progress, next step
- the scope the user granted, quoted verbatim, so the next agent does not ask again
- running work: subagent ids, T3 task ids, background commands, PRs being watched
- open questions still waiting for the user
- a "suggested skills" section listing the skills the next agent should invoke

Do not duplicate what other artifacts hold (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL.

Redact secrets and personal data.

If the user passed arguments, they describe what the next session will focus on. Tailor the document to it.

## Delegate the thread

Use the means the current tools offer to start the next agent with the document as its brief.

- **Tools available**: a thread-launch tool (`mcp__t3-code__t3_thread_launch` when it loads: ToolSearch `select:` once), a delegated-task tool, or a worktree-bound thread for isolated work. If the user asked for a new thread or agent, launch it now. Otherwise offer it in one line.
- **No such tool**: hand over a paste-ready prompt.

Always end by printing:
1. the absolute path of the document
2. a one-line start prompt: `Read <absolute path> and continue: <next step>.`
3. the link or id of the launched thread, if one was launched
