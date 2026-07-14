#!/usr/bin/env python3
"""Pin sync_blocks.py's behaviors so a refactor cannot silently disarm the gate.

Runs on stdlib only (unittest + tempfile): `python3 scripts/test_sync_blocks.py`.
Each test builds a scratch tree and drives the script through --root, asserting on
exit code AND message content — the gate's contract is both.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "sync_blocks.py"

GOOD_RULE = """\
# A rule

<!-- block: deps -->
```toml
dependencies = ["fastapi>=0.118"]
```
<!-- /block -->
"""

GOOD_SKILL = """\
---
name: demo
---

<!-- include: rules/python.md#deps -->
```toml
dependencies = ["fastapi>=0.118"]
```
<!-- /include -->
"""


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
    )


class Tree:
    """Minimal repo shape: rules/*.md + skills/*/SKILL.md."""

    def __init__(self, root: Path, rule: str = GOOD_RULE, skill: str = GOOD_SKILL) -> None:
        self.root = root
        (root / "rules").mkdir()
        (root / "skills" / "demo").mkdir(parents=True)
        self.rule = root / "rules" / "python.md"
        self.skill = root / "skills" / "demo" / "SKILL.md"
        self.rule.write_text(rule)
        self.skill.write_text(skill)


class SyncBlocksTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tree = Tree(Path(self._tmp.name))

    # --- happy path -------------------------------------------------------------------------

    def test_clean_tree_passes(self) -> None:
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("blocks in sync (1 include site(s)", r.stdout)

    def test_fix_is_idempotent(self) -> None:
        before = self.tree.skill.read_text()
        for _ in range(2):
            self.assertEqual(run(self.tree.root, "--fix").returncode, 0)
        self.assertEqual(self.tree.skill.read_text(), before)

    # --- drift ------------------------------------------------------------------------------

    def test_drift_fails_and_fix_repairs(self) -> None:
        self.tree.skill.write_text(self.tree.skill.read_text().replace("0.118", "0.115"))
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("has drifted", r.stdout)
        self.assertEqual(run(self.tree.root, "--fix").returncode, 0)
        self.assertIn("0.118", self.tree.skill.read_text())
        self.assertEqual(run(self.tree.root).returncode, 0)

    def test_include_in_rules_is_checked_too(self) -> None:
        other = self.tree.root / "rules" / "other.md"
        other.write_text("<!-- include: rules/python.md#deps -->\nWRONG\n<!-- /include -->\n")
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1, "an include inside rules/ must be drift-checked")
        self.assertIn("rules/other.md", r.stdout)

    # --- marker integrity (the --fix-eats-content class) --------------------------------------

    def test_missing_close_marker_is_fatal_and_fix_refuses(self) -> None:
        self.tree.skill.write_text(self.tree.skill.read_text().replace("<!-- /include -->", ""))
        before = self.tree.skill.read_text()
        for args in ((), ("--fix",)):
            r = run(self.tree.root, *args)
            self.assertEqual(r.returncode, 1, f"{args}: lost close marker must be fatal")
            self.assertIn("markers are broken", r.stdout)
        self.assertEqual(self.tree.skill.read_text(), before, "--fix must not touch a broken file")

    def test_prose_mention_of_marker_is_not_counted(self) -> None:
        # Docs legitimately write `<!-- include: -->` inside backticks mid-line.
        self.tree.skill.write_text("Prose mentioning `<!-- include: -->` markers.\n\n" + GOOD_SKILL)
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_balanced_counts_but_misspanned_markers_are_fatal(self) -> None:
        # opens == closes but only ONE well-formed region: the first close pairs with the first
        # open, swallowing the second open inside its body. Equal counts alone would pass this —
        # the `matched` term of the integrity check is the sole guard, and without it --fix
        # destroys the swallowed region. (This exact mutant survived the suite once.)
        self.tree.skill.write_text(
            "<!-- include: rules/python.md#deps -->\nX\n"
            "<!-- include: rules/python.md#deps -->\nPRECIOUS\n"
            "<!-- /include -->\n<!-- /include -->\n"
        )
        before = self.tree.skill.read_text()
        for args in ((), ("--fix",)):
            r = run(self.tree.root, *args)
            self.assertEqual(r.returncode, 1, f"{args}: mis-spanned markers must be fatal")
            self.assertIn("markers are broken", r.stdout)
        self.assertEqual(self.tree.skill.read_text(), before, "--fix must not touch it")

    def test_prose_mention_of_close_marker_is_not_counted(self) -> None:
        # Same anchor requirement as the open tag: `<!-- /include -->` inside backticks mid-line
        # must not unbalance the counts.
        self.tree.skill.write_text("Prose mentioning `<!-- /include -->` markers.\n\n" + GOOD_SKILL)
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_missing_block_close_marker_is_fatal(self) -> None:
        self.tree.rule.write_text(self.tree.rule.read_text().replace("<!-- /block -->", ""))
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("markers are broken", r.stdout)

    def test_deleting_include_markers_disarms_nothing_silently(self) -> None:
        # Copy kept, markers removed: the block becomes "never included" — must be a hard error.
        text = self.tree.skill.read_text()
        text = text.replace("<!-- include: rules/python.md#deps -->\n", "")
        text = text.replace("<!-- /include -->", "")
        self.tree.skill.write_text(text)
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1, "unused canonical block must fail, not note")
        self.assertIn("never included", r.stdout)

    # --- canonical block validation -----------------------------------------------------------

    def test_unbalanced_fence_in_block_fails(self) -> None:
        self.tree.rule.write_text(GOOD_RULE.replace('dependencies = ["fastapi>=0.118"]\n```\n', ""))
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("odd number of ``` fences", r.stdout)

    def test_invalid_toml_in_block_fails(self) -> None:
        self.tree.rule.write_text(GOOD_RULE.replace('["fastapi>=0.118"]', '["fastapi>=0.118"'))
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not parse", r.stdout)

    def test_invalid_python_in_block_fails(self) -> None:
        self.tree.rule.write_text("<!-- block: code -->\n```python\ndef broken(:\n```\n<!-- /block -->\n")
        self.tree.skill.write_text(
            "<!-- include: rules/python.md#code -->\n```python\ndef broken(:\n```\n<!-- /include -->\n"
        )
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("fenced python does not parse", r.stdout)

    def test_duplicate_block_names_are_all_reported(self) -> None:
        self.tree.rule.write_text(GOOD_RULE + "\n" + GOOD_RULE)  # same name declared twice
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate block", r.stdout)

    # --- includes pointing nowhere -------------------------------------------------------------

    def test_missing_block_target_fails_without_fix_advice(self) -> None:
        self.tree.skill.write_text(
            GOOD_SKILL + "\n<!-- include: rules/python.md#ghost -->\nx\n<!-- /include -->\n"
        )
        r = run(self.tree.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no file declares", r.stdout)
        self.assertNotIn("Run `python3 scripts/sync_blocks.py --fix`", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
