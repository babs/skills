#!/usr/bin/env python3
"""Pin validate-skills.sh's bash checks (frontmatter, rule refs, pin uniformity) so a refactor of
the awk/grep/sed cannot silently disarm them while CI stays green.

Each test builds a scratch repo, copies the scripts in, and runs the scratch copy of the script
with VALIDATE_SKILLS_NO_SELFTEST=1 (breaking the self-test recursion).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

GOOD_SKILL = """\
---
name: demo
description: does demo things
allowed-tools: Read, Bash
version: "1.0.0"
---

Body referencing ${CLAUDE_PLUGIN_ROOT}/rules/python.md.
"""

GOOD_RULE = "# rule\n\nCOPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv\n"


def make_tree(root: Path, skill: str = GOOD_SKILL, rule: str = GOOD_RULE) -> None:
    (root / "rules").mkdir()
    (root / "skills" / "demo").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "rules" / "python.md").write_text(rule)
    (root / "skills" / "demo" / "SKILL.md").write_text(skill)
    for f in ("validate-skills.sh", "sync_blocks.py"):
        shutil.copy(SCRIPTS / f, root / "scripts" / f)


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "scripts" / "validate-skills.sh")],
        capture_output=True,
        text=True,
        env={**os.environ, "VALIDATE_SKILLS_NO_SELFTEST": "1"},
    )


class ValidateSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        make_tree(self.root)

    def test_clean_tree_passes(self) -> None:
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skills validation passed", r.stdout)

    def test_missing_allowed_tools_fails(self) -> None:
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(skill.read_text().replace("allowed-tools: Read, Bash\n", ""))
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("allowed-tools", r.stdout)

    def test_bogus_rule_reference_fails(self) -> None:
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(skill.read_text() + "\nAlso ${CLAUDE_PLUGIN_ROOT}/rules/ghost.md.\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ghost.md", r.stdout)

    def test_missing_name_fails(self) -> None:
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(skill.read_text().replace("name: demo\n", ""))
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("'name'", r.stdout)

    def test_missing_description_fails(self) -> None:
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(skill.read_text().replace("description: does demo things\n", ""))
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("'description'", r.stdout)

    def test_empty_field_value_fails(self) -> None:
        # `allowed-tools:` with no value must fail — the regex requires a non-space after the key.
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(skill.read_text().replace("allowed-tools: Read, Bash", "allowed-tools:"))
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("allowed-tools", r.stdout)

    def test_folded_scalar_description_passes(self) -> None:
        # Repo convention: `description: >-` folded scalars must satisfy the frontmatter check.
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(
            skill.read_text().replace(
                "description: does demo things\n",
                "description: >-\n  does demo things\n  across two lines\n",
            )
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_rule_ref_followed_by_sentence_period_passes(self) -> None:
        # The grep is anchored on `.md`; without the anchor "rules/python.md." would be looked up
        # verbatim and false-fail. Pins the anchor.
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(skill.read_text() + "\nSee ${CLAUDE_PLUGIN_ROOT}/rules/python.md.\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_diverged_python_image_pin_fails(self) -> None:
        (self.root / "rules" / "img.md").write_text("# img\n\nFROM python:3.14-slim-trixie\n")
        (self.root / "rules" / "img2.md").write_text("# img2\n\nFROM python:3.13-slim-bookworm\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("diverges", r.stdout)

    def test_diverged_pin_fails(self) -> None:
        (self.root / "rules" / "docker.md").write_text(
            "# other\n\nCOPY --from=ghcr.io/astral-sh/uv:0.9.6 /uv /usr/local/bin/uv\n"
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("diverges", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
