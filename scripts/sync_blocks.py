#!/usr/bin/env python3
"""Keep the text that lives in more than one file from drifting apart.

A file (usually a rule; a skill may too, e.g. shared review doctrine) owns a canonical block:

    <!-- block: engine -->
    ```python
    ...
    ```
    <!-- /block -->

Any other file under rules/ or skills/ includes it by reference, carrying a copy so it still
reads standalone:

    <!-- include: rules/postgres.md#engine -->
    ```python
    ...same bytes...
    ```
    <!-- /include -->

Run with no arguments (what CI and pre-commit do) to fail on ANY of: a drifted copy, a canonical
block that is not a well-formed unit (unbalanced ``` fences; EVERY fenced toml/python segment must
parse), unbalanced or orphaned markers (a lost `<!-- /include -->` must be a hard error — the
regex would otherwise swallow everything up to the NEXT close marker, and `--fix` would then
destroy that span), a declared block that nothing includes (that is how a gate gets disarmed:
delete the include markers and the copy silently stops being checked), or an include whose block
no file declares.

`--fix` rewrites the copies from their canonical blocks — and refuses to run while any marker
integrity error is present. `--root <dir>` overrides the repo root (used by the test suite).

WHY this exists: every duplicated block in this repo has drifted at least once (fastapi>=0.115 vs
>=0.118; four different `useradd` invocations; two divergent Dockerfiles). "Remember to keep them
in sync" is not a mechanism — this is. Its own behaviors are pinned by scripts/test_sync_blocks.py.
Note: files are read with universal newlines, so --fix rewrites a CRLF file as LF (the
mixed-line-ending pre-commit hook enforces LF anyway).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import tempfile
import tomllib
from pathlib import Path

BLOCK_RE = re.compile(r"<!-- block: (?P<name>[\w.-]+) -->\n(?P<body>.*?)<!-- /block -->", re.DOTALL)
INCLUDE_RE = re.compile(
    r"(?P<open><!-- include: (?P<src>[\w./-]+)#(?P<name>[\w.-]+) -->\n)"
    r"(?P<body>.*?)"
    r"(?P<close><!-- /include -->)",
    re.DOTALL,
)

# Languages whose fenced content we can prove well-formed. Others (dockerfile, sql, makefile,
# plain markdown) only get the fence-balance check.
PARSERS = {
    "toml": tomllib.loads,
    "python": lambda src: ast.parse(src),
}


def sources(root: Path) -> list[Path]:
    return sorted((root / "rules").glob("*.md")) + sorted((root / "skills").glob("*/SKILL.md"))


def marker_integrity(rel: str, text: str) -> list[str]:
    """Orphaned/unbalanced markers make the regexes mis-span: refuse before touching anything.

    Markers are counted line-anchored: prose may legitimately MENTION `<!-- include: -->` inside
    backticks mid-line, and a real marker anywhere but line-start would mis-span the regions
    anyway (the well-formed count then disagrees, which is exactly what gets flagged)."""
    errors: list[str] = []
    for kind, open_tag, close_tag, matcher in (
        ("block", "<!-- block:", "<!-- /block -->", BLOCK_RE),
        ("include", "<!-- include:", "<!-- /include -->", INCLUDE_RE),
    ):
        opens = len(re.findall(rf"^{re.escape(open_tag)}", text, re.MULTILINE))
        closes = len(re.findall(rf"^{re.escape(close_tag)}", text, re.MULTILINE))
        matched = len(matcher.findall(text))
        if not (opens == closes == matched):
            errors.append(
                f"{rel}: {kind} markers are broken ({opens} opener(s), {closes} closer(s), "
                f"{matched} well-formed region(s)) — a lost or malformed marker here would make "
                "--fix destroy content; repair the markers by hand first"
            )
    return errors


def validate_block(where: str, name: str, body: str) -> list[str]:
    """Structural checks a byte-diff cannot make: the block must be a self-contained unit."""
    errors: list[str] = []
    lines = body.splitlines()
    fence_idx = [i for i, line in enumerate(lines) if line.startswith("```")]
    if len(fence_idx) % 2:
        errors.append(
            f"{where}#{name}: odd number of ``` fences ({len(fence_idx)}) — "
            "the block boundary cuts through a code fence"
        )
        return errors  # fence pairing is broken; language checks would be meaningless
    for open_i, close_i in zip(fence_idx[::2], fence_idx[1::2]):
        lang = lines[open_i].removeprefix("```").strip()
        parser = PARSERS.get(lang)
        if parser is None:
            continue
        content = "\n".join(lines[open_i + 1 : close_i])
        try:
            parser(content)
        except (tomllib.TOMLDecodeError, SyntaxError) as exc:
            errors.append(
                f"{where}#{name}: fenced {lang} does not parse ({exc}) — "
                "the canonical content is corrupt; fix the block, not the copies"
            )
    return errors


def atomic_write(path: Path, content: str) -> None:
    """A crash mid-write must not truncate a source file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix", action="store_true", help="rewrite the copies from their canonical blocks")
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repo root (tests point this at a scratch tree)",
    )
    args = ap.parse_args()
    root: Path = args.root

    texts = {src: src.read_text() for src in sources(root)}
    rels = {src: str(src.relative_to(root)) for src in texts}

    # Pass 1 — marker integrity everywhere. Nothing else is trustworthy until this holds.
    errors: list[str] = []
    for src, text in texts.items():
        errors += marker_integrity(rels[src], text)
    if errors:
        for problem in errors:
            print(f"ERROR: {problem}")
        return 1

    # Pass 2 — collect canonical blocks (any source file may declare them) and validate each.
    blocks: dict[tuple[str, str], str] = {}
    for src, text in texts.items():
        for m in BLOCK_RE.finditer(text):
            key = (rels[src], m.group("name"))
            if key in blocks:
                errors.append(f"{rels[src]}: duplicate block '{m.group('name')}'")
                continue
            blocks[key] = m.group("body")
            errors += validate_block(rels[src], m.group("name"), m.group("body"))
    if errors:
        for problem in errors:
            print(f"ERROR: {problem}")
        return 1

    # Pass 3 — walk every include site, in rules/ and skills/ alike.
    drifted: list[str] = []
    fixed: list[str] = []
    missing: list[str] = []
    used: set[tuple[str, str]] = set()
    n_sites = 0

    for src, text in texts.items():
        rel = rels[src]
        changed = False

        def replace(m: re.Match[str]) -> str:
            nonlocal changed, n_sites
            n_sites += 1
            key = (m.group("src"), m.group("name"))
            used.add(key)
            if key not in blocks:
                # --fix cannot repair this: there is no canonical content to inject.
                missing.append(
                    f"{rel}: includes {key[0]}#{key[1]}, which no file declares — "
                    "fix the reference (or declare the block) by hand"
                )
                return m.group(0)
            want = blocks[key]
            if m.group("body") != want:
                if args.fix:
                    changed = True
                    return m.group("open") + want + m.group("close")
                drifted.append(f"{rel}: {key[0]}#{key[1]} has drifted from its canonical block")
            return m.group(0)

        new = INCLUDE_RE.sub(replace, text)
        if changed:
            atomic_write(src, new)
            fixed.append(rel)

    # A block nobody includes is a disarmed gate (the copy that used to be checked no longer is)
    # or dead weight. Either way: hard error, not a note.
    for key in sorted(set(blocks) - used):
        errors.append(
            f"{key[0]}#{key[1]} is declared but never included — if its copy lost its include "
            "markers the gate is disarmed; if it is genuinely standalone, un-block it"
        )

    for problem in missing + drifted + errors:
        print(f"ERROR: {problem}")
    if drifted:
        print("\nRun `python3 scripts/sync_blocks.py --fix` — the canonical block wins.")
    if missing or drifted or errors:
        return 1

    if fixed:
        print("synced from canonical blocks: " + ", ".join(fixed))
    else:
        print(f"blocks in sync ({n_sites} include site(s) across {len(blocks)} canonical block(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
