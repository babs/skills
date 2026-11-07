#!/usr/bin/env python3
"""Search Claude Code transcripts for a regex in user/assistant text, grouped per session."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
SNIPPET = 80
# Harness-injected text stored as user turns (agent results, reminders), not typed by anyone.
HARNESS_PREFIXES = ("<task-notification", "<system-reminder", "<local-command", "Caveat:")


@dataclass
class Hit:
    ts: str
    cwd: str
    session: str
    title: str | None
    count: int
    snippets: list[str]


def texts(content: object) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b["text"] for b in content if isinstance(b, dict) and isinstance(b.get("text"), str)]
    return []


def snippet(text: str, m: re.Match[str]) -> str:
    start, end = max(0, m.start() - SNIPPET), m.end() + SNIPPET
    return " ".join(text[start:end].split())


def scan(path: Path, rx: re.Pattern[str], markers: tuple[str, ...]) -> Hit | None:
    titles: dict[str, str] = {}
    cwd, first_ts, count = "", "", 0
    snippets: list[str] = []
    with path.open(errors="replace") as f:
        for line in f:
            is_title = line.startswith(('{"type":"custom-title"', '{"type":"ai-title"'))
            # Only message lines carry searchable text; tool results are file dumps, not conversation.
            if not is_title and (not any(mk in line for mk in markers) or '"tool_use_id"' in line):
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not isinstance(e, dict):
                continue
            if is_title:
                titles[e["type"]] = e.get("customTitle") or e.get("aiTitle") or ""
                continue
            if e.get("isSidechain") or e.get("isMeta"):
                continue
            cwd = cwd or e.get("cwd", "")
            msg = e.get("message")
            for t in texts(msg.get("content") if isinstance(msg, dict) else None):
                if t.startswith(HARNESS_PREFIXES):
                    continue
                m = rx.search(t)
                if m:
                    count += 1
                    first_ts = first_ts or e.get("timestamp", "")
                    if len(snippets) < 2:
                        snippets.append(f"{e['type'][0].upper()}: {snippet(t, m)}")
    if not count:
        return None
    title = titles.get("custom-title") or titles.get("ai-title")
    return Hit(first_ts, cwd or path.parent.name, path.stem, title, count, snippets)


def search(root: Path, rx: re.Pattern[str], days: int, project: str | None, role: str) -> list[Hit]:
    cutoff = time.time() - days * 86400
    roles = ("user", "assistant") if role == "all" else (role,)
    markers = tuple(f'"type":"{r}"' for r in roles)
    hits: list[Hit] = []
    for path in root.glob("*/*.jsonl"):
        # -tmp-* dirs are T3 title-generation runs: copies of real prompts, not conversations.
        if path.parent.name.startswith("-tmp-") or (project and project not in path.parent.name):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                continue
            hit = scan(path, rx, markers)
        except OSError:
            continue  # file rotated or removed during the scan
        if hit:
            hits.append(hit)
    return sorted(hits, key=lambda h: h.ts, reverse=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pattern", help="case-insensitive regex")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--project", help="substring of the project directory name")
    p.add_argument("--role", choices=["user", "assistant", "all"], default="all")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    a = p.parse_args()
    try:
        rx = re.compile(a.pattern, re.IGNORECASE | re.MULTILINE)
    except re.error as e:
        print(f"bad regex: {e}", file=sys.stderr)
        return 2
    if not a.root.is_dir():
        print(f"no transcripts at {a.root}", file=sys.stderr)
        return 1
    hits = search(a.root, rx, a.days, a.project, a.role)
    try:
        for h in hits[: a.limit]:
            print(f"{h.ts[:16]}  {h.session}  [{h.title or '-'}]  hits={h.count}  cwd={h.cwd}")
            for s in h.snippets:
                print(f"    {s}")
        sys.stdout.flush()
    except BrokenPipeError:
        # Reader (head, less) closed early: not an error. Point stdout at devnull so the exit flush is silent.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    print(f"{len(hits)} session(s) matched", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
