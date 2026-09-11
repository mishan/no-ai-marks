"""Regression cases collected from other projects' test suites and from real
commits, pull requests, and docs. Each line of tests/corpus/*.jsonl is one
case:

    {"id": "...", "source": "URL or repo path", "kind": "commit_message",
     "input": "...", "expected": "flag", "rule": "ai-trailer", "note": "..."}

kind is commit_message, commit_msg_file (a commit message file as a
commit-msg hook sees it, with # comment lines), pr_text, file, branch, or
author ("Name <email>"). expected is flag, pass (no findings), or warn
(warnings only, so the check still exits 0); rule, path (for files), and
note are optional. A pass case with a note records a deliberate choice not
to flag something another project flags.
"""

import json
import pathlib
import unittest

from helpers import scanner

from no_ai_marks.__main__ import strip_git_comments
from no_ai_marks.git import Commit
from no_ai_marks.registry import split_identity

CORPUS = pathlib.Path(__file__).parent / "corpus"


def run(case):
    s = scanner()
    kind, text = case["kind"], case["input"]
    if kind in ("commit_message", "pr_text"):
        s.text(text, case["id"])
    elif kind == "commit_msg_file":
        s.text(strip_git_comments(text), case["id"])
    elif kind == "file":
        s.file(case.get("path", "example.txt"), text.encode("utf-8"))
    elif kind == "branch":
        s.branch(text)
    elif kind == "author":
        name, email = split_identity(text)
        s.commit(Commit("0" * 40, name, email, "Jane Dev", "jane@example.com", "Change\n"))
    else:
        raise ValueError(f"unknown kind {kind!r}")
    return s.findings


class CorpusTest(unittest.TestCase):
    def test_cases(self):
        for path in sorted(CORPUS.glob("*.jsonl")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                case = json.loads(line)
                with self.subTest(file=path.name, line=number, id=case["id"]):
                    found = run(case)
                    if case["expected"] == "flag":
                        self.assertTrue(found, "not flagged")
                        if case.get("rule"):
                            self.assertIn(case["rule"], [f.rule for f in found])
                    elif case["expected"] == "warn":
                        self.assertTrue(found, "no warning")
                        self.assertEqual([f.rule for f in found if f.severity != "warning"], [])
                    else:
                        self.assertEqual([f"{f.rule}: {f.message}" for f in found], [])


if __name__ == "__main__":
    unittest.main()
