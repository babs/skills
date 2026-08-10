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

    def test_valid_section_reference_passes(self) -> None:
        # A pointer whose heading exists must not false-fail — the heading carries a trailing
        # "(canonical for …)" the pointer deliberately omits, so the match is a substring.
        (self.root / "rules" / "python.md").write_text(
            GOOD_RULE + "\n## Flat layout (canonical for demo)\n\nbody\n"
        )
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(
            skill.read_text() + '\nCopy `${CLAUDE_PLUGIN_ROOT}/rules/python.md` ("Flat layout").\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_renamed_rule_section_fails(self) -> None:
        # The drift this gate exists for: a skill that POINTS at a heading instead of carrying a
        # copy rots silently when the heading is renamed — the file still exists, so check 2 passes.
        (self.root / "rules" / "python.md").write_text(GOOD_RULE + "\n## Renamed layout\n\nbody\n")
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(
            skill.read_text() + '\nCopy `${CLAUDE_PLUGIN_ROOT}/rules/python.md` ("Flat layout").\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Flat layout", r.stdout)

    def test_section_reference_with_punctuation_is_literal(self) -> None:
        # Section names carry regex metacharacters (".dockerignore", em dashes). -F keeps them
        # literal: without it, "." would match any character and a rotted pointer could pass.
        (self.root / "rules" / "python.md").write_text(GOOD_RULE + "\n## Xdockerignore\n\nbody\n")
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(
            skill.read_text() + '\nCopy `${CLAUDE_PLUGIN_ROOT}/rules/python.md` (".dockerignore").\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn(".dockerignore", r.stdout)

    # --- Fence/frontmatter policy: one test per row of the table in validate-skills.sh. The policy
    # --- deliberately differs per consumer; these three lock it so it cannot silently flip again.

    def test_policy_row1_existence_includes_fenced_references(self) -> None:
        # check 2 | does this path exist? | fences INCLUDED — a typo is a typo inside a code example.
        (self.root / "skills" / "demo" / "SKILL.md").write_text(
            GOOD_SKILL + "\n```dockerfile\n# see rules/ghost.md for the rationale\n```\n"
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("rules/ghost.md", r.stdout)

    def test_policy_row2_enforcement_excludes_fenced_pointers(self) -> None:
        # 2b source | is this a pointer to enforce? | fences excluded — a fenced pointer documents
        # the form; it does not assert the heading exists.
        self._add_skill("caller", '\n```markdown\nCopy `rules/python.md` ("Ghost Heading") verbatim.\n```\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_policy_row3_headings_exclude_fences_and_frontmatter(self) -> None:
        # 2b target | is this line a heading? | fences AND frontmatter excluded.
        (self.root / "skills" / "other").mkdir(parents=True)
        (self.root / "skills" / "other" / "SKILL.md").write_text(
            "---\nname: other\n# Ghost Heading in frontmatter\ndescription: d\nallowed-tools: Read\n---\n\n"
            "```markdown\n# Ghost Heading in a fence\n```\n\n## Real Heading\n\nbody\n"
        )
        self._add_skill("caller", '\nSee `skills/other/SKILL.md` ("Ghost Heading").\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("no heading there matches", r.stdout)

    def test_section_in_code_fence_does_not_satisfy_pointer(self) -> None:
        # The bypass this filter exists for: the heading was renamed away, but a comment inside a
        # fenced example still contains the string. Matching any `#` line would pass a dangling
        # pointer. Hash-counting cannot fix it — `# Flat layout stage` and an H1 are both `# text`.
        (self.root / "rules" / "python.md").write_text(
            GOOD_RULE + "\n## Renamed\n\n```dockerfile\n# Flat layout stage\nFROM scratch\n```\n"
        )
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(
            skill.read_text() + '\nCopy `${CLAUDE_PLUGIN_ROOT}/rules/python.md` ("Flat layout").\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Flat layout", r.stdout)

    def test_ambiguous_section_reference_fails(self) -> None:
        # A pointer that matches two headings resolves to whichever the reader picks: not a pointer.
        (self.root / "rules" / "python.md").write_text(
            GOOD_RULE + "\n## Build step — flat\n\nx\n\n## Build step — packaged\n\ny\n"
        )
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(
            skill.read_text() + '\nSee `${CLAUDE_PLUGIN_ROOT}/rules/python.md` ("Build step").\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("matches 2 headings", r.stdout)

    def test_missing_rule_to_rule_reference_fails(self) -> None:
        # Rule→rule pointers used to be ungated ("double-check the target exists" — a promise, not
        # a check). A bare rules/<f>.md path in a rule now has to resolve like any other.
        (self.root / "rules" / "python.md").write_text(GOOD_RULE + "\nSee rules/ghost.md as well.\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ghost.md", r.stdout)

    def _add_skill(self, name: str, body: str) -> None:
        (self.root / "skills" / name).mkdir(parents=True, exist_ok=True)
        (self.root / "skills" / name / "SKILL.md").write_text(
            GOOD_SKILL.replace("name: demo", f"name: {name}") + body
        )

    def test_valid_skill_section_pointer_passes(self) -> None:
        self._add_skill("other", "\n## Some Heading — with a trailing clause\n\nbody\n")
        self._add_skill("caller", '\nFollow `skills/other/SKILL.md` ("Some Heading") verbatim.\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_renamed_skill_section_fails(self) -> None:
        # A prose trim deleted two skill section headings, so skill targets need the same check as
        # rule targets — otherwise a skill->skill pointer rots with CI green.
        self._add_skill("other", "\n## Renamed Heading\n\nbody\n")
        self._add_skill("caller", '\nFollow `skills/other/SKILL.md` ("Some Heading") verbatim.\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Some Heading", r.stdout)

    def test_pointer_to_missing_skill_file_fails(self) -> None:
        # Assert the existence message specifically: "ghost" alone was satisfied by the weaker
        # "no heading there matches" that a deleted existence branch would emit instead.
        self._add_skill("caller", '\nFollow `skills/ghost/SKILL.md` ("Some Heading") verbatim.\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("references skills/ghost/SKILL.md, which does not exist", r.stdout)

    def test_bare_skill_reference_must_exist(self) -> None:
        # A skill reference with no ("Section") is a first-class reference now, so check 2 owns it.
        self._add_skill("caller", "\nSee `skills/ghost/SKILL.md` for details.\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("references skills/ghost/SKILL.md, which does not exist", r.stdout)

    def test_line_wrapped_pointer_is_checked(self) -> None:
        # The repo hard-wraps prose at ~100 cols, so a cosmetic reflow used to disarm the check.
        self._add_skill("other", "\n## Real Heading\n\nbody\n")
        self._add_skill("caller", '\nThe bar lives in `skills/other/SKILL.md`\n("Ghost Heading") — wrapped.\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Ghost Heading", r.stdout)

    def test_frontmatter_comment_does_not_satisfy_pointer(self) -> None:
        # `#` lines in YAML frontmatter are not headings; counting them let a rotted pointer pass.
        (self.root / "skills" / "other").mkdir(parents=True)
        (self.root / "skills" / "other" / "SKILL.md").write_text(
            "---\nname: other\n# Ghost Heading appears only in this comment\n"
            "description: does things\nallowed-tools: Read\n---\n\n## Real Heading\n\nbody\n"
        )
        self._add_skill("caller", '\nSee `skills/other/SKILL.md` ("Ghost Heading").\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Ghost Heading", r.stdout)

    def test_pointer_inside_a_fence_is_not_enforced(self) -> None:
        # A pointer shown inside a fence is documentation of the form, not a live pointer —
        # otherwise the form becomes undocumentable inside a skill or rule.
        self._add_skill("caller", '\n```markdown\nCopy `rules/python.md` ("Ghost Heading") verbatim.\n```\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_rotted_pointer_in_a_rule_source_fails(self) -> None:
        # rules/ is scanned as a pointer SOURCE too; dropping that argument left the suite green.
        (self.root / "rules" / "other.md").write_text("# other\n\n## Real Heading\n\nbody\n")
        (self.root / "rules" / "python.md").write_text(
            GOOD_RULE + '\nSee `rules/other.md` ("Ghost Heading") for details.\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Ghost Heading", r.stdout)

    def _go_pair(self, std_vars: str, scaffold_vars: str) -> None:
        (self.root / "rules" / "golang.md").write_text(f"# go\n\n```go\nvar (\n{std_vars})\n```\n")
        (self.root / "skills" / "go-init").mkdir(parents=True, exist_ok=True)
        (self.root / "skills" / "go-init" / "SKILL.md").write_text(
            GOOD_SKILL + f"\n```go\nvar (\n{scaffold_vars})\n```\n"
        )

    def test_go_standard_without_its_scaffolder_fails(self) -> None:
        # Requiring BOTH files silently disarmed 2c: renaming go-init turned the check off.
        (self.root / "rules" / "golang.md").write_text('# go\n\n```go\nvar (\n\tVersion = "v0.0.0"\n)\n```\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("counterpart exists", r.stdout)

    def test_later_checks_still_run_alongside_a_go_var_drift(self) -> None:
        # 2c's report was a bare `diff | sed` under `set -euo pipefail`: a drift aborted the script
        # and every later check (block drift, pins, selftests) was silently skipped.
        self._go_pair('\tVersion = "v0.0.0"\n\tBuilder = "unknown"\n', '\tVersion = "v0.0.0"\n')
        (self.root / "rules" / "img.md").write_text(
            "# img\n\nCOPY --from=ghcr.io/astral-sh/uv:0.9.6 /uv /usr/local/bin/uv\n"
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Go build-time var set differs", r.stdout)
        self.assertIn("diverges", r.stdout)

    def test_english_possessive_is_not_a_pointer(self) -> None:
        # The regression this anchoring exists for: an unanchored pattern read `zap`'s "sugared" as
        # a pointer to a skill named zap and failed the commit on ordinary prose.
        self._add_skill("caller", '\nUse `zap`\'s "sugared" logger for brevity.\n')
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_missing_go_var_block_fails(self) -> None:
        # Both sides empty compare equal, which would pass a tree whose var block was restructured
        # away — the gate would stop gating silently.
        (self.root / "rules" / "golang.md").write_text("# go\n\nno var block here\n")
        (self.root / "skills" / "go-init").mkdir(parents=True)
        (self.root / "skills" / "go-init" / "SKILL.md").write_text(GOOD_SKILL + "\nnone either\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("no Go build-time var block", r.stdout)

    def test_go_build_var_set_drift_fails(self) -> None:
        # The exact drift that lost `Builder`: rules/golang.md declared it, the go-init template
        # did not, and nothing noticed. These two cannot be a sync_blocks shared block (the skill's
        # copy sits inside main.go's ```go fence), so the identifier SETS are compared instead.
        (self.root / "rules" / "golang.md").write_text(
            "# go\n\n```go\nvar (\n\tVersion = \"v0.0.0\"\n\tBuilder = \"unknown\"\n)\n```\n"
        )
        (self.root / "skills" / "go-init").mkdir(parents=True)
        (self.root / "skills" / "go-init" / "SKILL.md").write_text(
            GOOD_SKILL + '\n```go\nvar (\n\tVersion = "v0.0.0"\n)\n```\n'  # Builder missing
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Go build-time var set differs", r.stdout)
        self.assertIn("Builder", r.stdout)

    def test_matching_go_build_var_set_passes(self) -> None:
        # Agreement must not depend on byte-identity: same identifiers, different indentation and
        # different default values still pass — only the SET is normative.
        (self.root / "rules" / "golang.md").write_text(
            "# go\n\n```go\nvar (\n    Version = \"v0.0.0\"\n    Builder = \"unknown\"\n)\n```\n"
        )
        (self.root / "skills" / "go-init").mkdir(parents=True)
        (self.root / "skills" / "go-init" / "SKILL.md").write_text(
            GOOD_SKILL + '\n```go\nvar (\n\tVersion = "dev"\n\tBuilder = "n/a"\n)\n```\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_diverged_python_image_pin_fails(self) -> None:
        (self.root / "rules" / "img.md").write_text("# img\n\nFROM python:3.14-slim-trixie\n")
        (self.root / "rules" / "img2.md").write_text("# img2\n\nFROM python:3.13-slim-bookworm\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("diverges", r.stdout)

    def test_retired_command_form_in_docs_fails(self) -> None:
        # The exact drift this gate exists for: md2clip dropped the hex-through-xargs macOS
        # clipboard form (BSD xargs -S caps -I replacement at 255 bytes), but SKILL.md kept
        # prescribing it as the fallback. Doc rot in a copy-paste table is a shipped bug.
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(
            skill.read_text() + "\n| macOS | `pandoc -t html | hexdump -ve '1/1 \"%.2x\"' | xargs ...` |\n"
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("retired command form", r.stdout)

    def test_retired_applescript_data_literal_in_docs_fails(self) -> None:
        # Second retired form, pinned separately: the alternation must not regress to one branch.
        (self.root / "rules" / "clip.md").write_text(
            "# clip\n\nosascript -e 'set the clipboard to «data HTML00»'\n"
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("retired command form", r.stdout)

    def test_bare_gfm_html_pandoc_form_fails(self) -> None:
        # md2clip's --selftest returns before pandoc is reached, so dropping --wrap=none from the
        # script (or from the copy-paste fallback table) is invisible to every other gate.
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(skill.read_text() + "\n| X11 | `pandoc -f gfm -t html | xclip -i` |\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing --no-highlight/--wrap=none", r.stdout)

    def test_flagged_gfm_html_pandoc_form_passes(self) -> None:
        skill = self.root / "skills" / "demo" / "SKILL.md"
        skill.write_text(
            skill.read_text() + "\n`pandoc -f gfm -t html --no-highlight --wrap=none | xclip -i`\n"
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_instrumentors_without_distro_fails(self) -> None:
        # The v1.9.0 defect: the canonical stack listed api/sdk/instrumentors/exporter but not the
        # distro, so opentelemetry-instrument found no configurator entry point and exported
        # nothing — while the app's own logs still showed real trace ids. Invisible without a gate.
        (self.root / "rules" / "py.md").write_text(
            '# py\n\n```toml\ndependencies = [\n    "opentelemetry-sdk>=1.29",\n'
            '    "opentelemetry-instrumentation-fastapi>=0.50b0",\n]\n```\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("opentelemetry-distro", r.stdout)

    def test_instrumentors_with_distro_passes(self) -> None:
        # The gate must accept the correct list, or it is just a ban on instrumentors.
        (self.root / "rules" / "py.md").write_text(
            '# py\n\n```toml\ndependencies = [\n    "opentelemetry-sdk>=1.29",\n'
            '    "opentelemetry-distro>=0.50b0",\n'
            '    "opentelemetry-instrumentation-fastapi>=0.50b0",\n]\n```\n'
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_otel_prose_without_deps_list_passes(self) -> None:
        # Prose ABOUT the packages is not a declaration: dockerfile-init discusses "OTel deps" and
        # opentelemetry-bootstrap without listing any. A gate that trips on it would be unusable.
        (self.root / "rules" / "docker2.md").write_text(
            "# d\n\nRun `.venv/bin/opentelemetry-bootstrap -a requirements`; "
            "no OTel deps -> drop the line.\n"
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_diverged_pin_fails(self) -> None:
        (self.root / "rules" / "docker.md").write_text(
            "# other\n\nCOPY --from=ghcr.io/astral-sh/uv:0.9.6 /uv /usr/local/bin/uv\n"
        )
        r = run(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("diverges", r.stdout)

    # --- check 6: review-template typography (two of its three characters are invisible) --------

    GOOD_TEMPLATE = (
        "### Critical\n\n"
        "∙ **C1.** {defect} `{file}:{line}` — {evidence}  \n"
        "  → **Fix (inst|class):** {the concrete change, one line}\n"
    )

    def _write_template(self, body: str) -> None:
        (self.root / "skills" / "demo" / "template.md").write_text(body)

    def test_intact_template_passes(self) -> None:
        self._write_template(self.GOOD_TEMPLATE)
        self.assertEqual(run(self.root).returncode, 0)

    def test_stripped_hard_break_fails(self) -> None:
        self._write_template(self.GOOD_TEMPLATE.replace("{evidence}  ", "{evidence}"))
        r = run(self.root)
        self.assertEqual(r.returncode, 1, "a lost trailing double space must be caught")
        self.assertIn("/ 0 hard", r.stdout)

    def test_nbsp_downgraded_to_spaces_fails(self) -> None:
        self._write_template(self.GOOD_TEMPLATE.replace("  ", "  "))
        r = run(self.root)
        self.assertEqual(r.returncode, 1, "NBSP replaced by plain spaces must be caught")
        # The counter, not the generic message: mutating the hard break instead would also
        # print "typography lost" and the test would pass while checking nothing.
        self.assertIn("/ 0 indented", r.stdout)

    def test_renamed_tiers_stay_gated(self) -> None:
        # The tier names are prose and have been renamed once; the guard must survive the next rename.
        renamed = self.GOOD_TEMPLATE.replace("(inst|class)", "(foo|bar)")
        self._write_template(renamed)
        self.assertEqual(run(self.root).returncode, 0)
        self._write_template(renamed.replace("\u00a0\u00a0", "  "))
        r = run(self.root)
        self.assertEqual(r.returncode, 1, "a renamed tier must not disarm the NBSP counter")
        self.assertIn("/ 0 indented", r.stdout)

    def test_prose_fix_example_is_not_counted_as_a_fix_line(self) -> None:
        # The real templates close with a comment showing a fix line in prose, plain-space indented.
        # Counting that as a fix line would make every intact template fail.
        self._write_template(
            self.GOOD_TEMPLATE
            + "\n<!--\n  \u2192 **Fix (inst):** {change} \u2014 a `class` fix exists\n-->\n"
        )
        self.assertEqual(run(self.root).returncode, 0)

    def test_finding_without_a_fix_line_fails(self) -> None:
        # The doctrine is "every finding names its fix"; a template that drops the fix line must not
        # pass just because the counters agree at zero.
        self._write_template("\n".join(self.GOOD_TEMPLATE.split("\n")[:-2]) + "\n")
        r = run(self.root)
        self.assertEqual(r.returncode, 1, "a finding with no fix line must be caught")
        self.assertIn("/ 0 indented", r.stdout)

    def test_reworded_placeholder_stays_gated(self) -> None:
        # The placeholder text is prose too; anchoring the counter on it would disarm the check.
        reworded = self.GOOD_TEMPLATE.replace("{the concrete change, one line}", "{the fix, one line}")
        self._write_template(reworded)
        self.assertEqual(run(self.root).returncode, 0)
        self._write_template(reworded.replace("\u00a0\u00a0", "  "))
        r = run(self.root)
        self.assertEqual(r.returncode, 1, "a reworded placeholder must not disarm the NBSP counter")
        self.assertIn("/ 0 indented", r.stdout)

    def test_template_without_the_glyph_is_not_checked(self) -> None:
        # A skill may ship a template that is not a finding report; check 6 must ignore it.
        self._write_template("### Report\n\n- item\n")
        self.assertEqual(run(self.root).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
