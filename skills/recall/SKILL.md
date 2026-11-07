---
name: recall
description: Use when the user says "recall the discussion on X", "search our conversations", "search my past conversations", "look at past discussions", "which conversation covered X", "find the original conversation", "search the other threads for X", "we covered this before", "search my shell history", or refers to earlier work, a past project or a past decision absent from this session. Not for the current repo's code or git history, nor the live state of running threads (sitrep).
# ToolSearch: T3 tools are deferred and must be loaded before the first call.
allowed-tools: Bash, Read, ToolSearch, mcp__t3-code__t3_project_list, mcp__t3-code__t3_thread_search, mcp__t3-code__t3_thread_read
version: "1.0.0"
---

# Recall

## Sources

Search every source that applies, in parallel.

1. **T3 threads**: `t3_thread_search` covers one project at a time. List projects with `t3_project_list`, search each with its `projectId`, then `t3_thread_read` the best hits.
2. **Claude Code transcripts**: `scripts/search.py` searches user and assistant text in `${CLAUDE_CONFIG_DIR:-~/.claude}/projects/*/*.jsonl`, subagents and `-tmp-*` project dirs excluded (`<skill-dir>` = this skill's directory):
   ```
   python3 -I <skill-dir>/scripts/search.py '<regex>' [--days 60] [--project <substr>] [--role user|assistant|all] [--limit 20]
   ```
   Newest first, one line per session: date, session id, title, hit count, cwd, then up to 2 snippets. The regex is case-insensitive, and `^`/`$` match at line starts and ends.
3. **Project memories**: `grep -ril '<term>' ${CLAUDE_CONFIG_DIR:-~/.claude}/projects/*/memory/`.
4. **Shell history**: `atuin search --limit 50 '<term>'` if installed, else the shell's history file.

Start with a narrow regex, then widen it with synonyms in the user's languages (`login|signin|sso`).

## Output

1. Ranked hits, one line each: date, where, what was decided or done.
2. The answer to the user's actual question, citing the hits.
3. How to resume, when relevant:
   - a T3 thread: `[title](t3-thread://v1/<threadId>)`
   - a Claude Code session: `claude --resume <sessionId>`, run from the `cwd` the script printed

## Rules

- Never search from `/` or the whole of `$HOME`.
- Transcripts can hold secrets. Never echo a token or a password, and quote at most 3 lines per hit.
- A recalled fact describes the past. Verify it live before acting on it.
- Hits can come from unrelated projects. Never copy them into commits, PRs, tickets or messages unless the user asks.
