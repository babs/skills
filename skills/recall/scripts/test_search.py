#!/usr/bin/env python3
"""search.py against a fake transcript tree."""

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from search import main, search


def turn(text: str, role: str = "user") -> str:
    message = {
        "type": role,
        "timestamp": "2026-01-02T03:04:05Z",
        "cwd": "/work",
        "message": {"content": text},
    }
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


class TranscriptCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        lines = [
            '{"type":"ai-title","aiTitle":"Generated title"}',
            '{"type":"custom-title","customTitle":"truncated',
            "[1, 2]",
            '{"type":"user","message":[1]}',
            '{"type":"user","message":{"content":[{"type":"text"}]}}',
            json.dumps({"type": "user", "isSidechain": True, "message": {"content": "side marker"}}),
            json.dumps({"type": "user", "isMeta": True, "message": {"content": "meta marker"}}),
            turn("foo bar"),
            turn("x\ndeploy now"),
            turn('say "quoted" here'),
            turn("assistant wording", "assistant"),
            turn("<task-notification>harness marker"),
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [{"type": "tool_result", "tool_use_id": "t", "content": "tool marker"}]
                    },
                }
            ),
        ]
        self.write("-work-proj/s1.jsonl", lines)
        self.write("-tmp-title-run/s2.jsonl", [turn("foo bar")])
        self.write("-work-proj/s1/subagents/s3.jsonl", [turn("foo bar")])
        self.write(
            "-work-other/s4.jsonl",
            [
                '{"type":"ai-title","aiTitle":"Generated"}',
                '{"type":"custom-title","customTitle":"Named"}',
                turn("foo later").replace("2026-01-02", "2026-02-02"),
            ],
        )

    def write(self, rel: str, lines: list[str]) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(lines) + "\n")

    def find(self, pattern: str, role: str = "all") -> list[str]:
        return [
            h.session
            for h in search(self.root, re.compile(pattern, re.IGNORECASE | re.MULTILINE), 3650, None, role)
        ]


class SearchTest(TranscriptCase):
    def test_matches_decoded_text_not_the_raw_json_line(self) -> None:
        for pattern in (r"foo\sbar", "^deploy", 'say "quoted"', "here$"):
            with self.subTest(pattern):
                self.assertEqual(self.find(pattern), ["s1"])

    def test_skips_tool_results_harness_text_and_tmp_dirs(self) -> None:
        self.assertEqual(self.find("tool marker"), [])
        self.assertEqual(self.find("harness marker"), [])
        self.assertEqual(self.find("foo bar"), ["s1"])
        self.assertEqual(self.find("side marker"), [])
        self.assertEqual(self.find("meta marker"), [])

    def test_role_filter(self) -> None:
        self.assertEqual(self.find("assistant wording", "user"), [])
        self.assertEqual(self.find("assistant wording", "assistant"), ["s1"])

    def test_survives_a_truncated_title_and_reads_ai_title(self) -> None:
        hit = search(self.root, re.compile("foo bar"), 3650, None, "all")[0]
        self.assertEqual((hit.title, hit.cwd), ("Generated title", "/work"))


class MainTest(TranscriptCase):
    def run_main(self, *args: str) -> str:
        out = io.StringIO()
        argv = ["search.py", *args, "--root", str(self.root), "--days", "3650"]
        with (
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        return out.getvalue()

    def test_flags_order_limit_project_and_title_precedence(self) -> None:
        self.assertIn("s1", self.run_main("^DEPLOY"))
        first = self.run_main("foo").splitlines()[0]
        self.assertIn("s4", first)
        self.assertIn("[Named]", first)
        self.assertNotIn("s1", self.run_main("foo", "--limit", "1"))
        self.assertNotIn("s4", self.run_main("foo", "--project", "work-proj"))

    def test_bad_regex_exits_2(self) -> None:
        with mock.patch.object(sys, "argv", ["search.py", "("]), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 2)


if __name__ == "__main__":
    unittest.main()
