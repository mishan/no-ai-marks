import json
import os
import tempfile
import unittest

from helpers import Repo

TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.repo.write("README.md", "# Demo\n")
        self.base = self.repo.commit("Initial commit")

    def tearDown(self):
        self.repo.cleanup()

    def findings(self, *args, env=None):
        code, out, err = self.repo.run(*args, "--format", "json", env=env)
        self.assertIn(code, (0, 1), err)
        return code, json.loads(out)


class RangeTest(RepoTestCase):
    def test_clean_range(self):
        self.repo.write("src/app.go", "package main\n")
        self.repo.commit("Add app")
        code, found = self.findings("range", "main~1")
        self.assertEqual((code, found), (0, []))

    def test_only_added_lines_are_checked(self):
        # The old line is someone else's problem; the new one is ours.
        self.repo.write("notes.md", "old\u200bline\n")
        base = self.repo.commit("Old")
        self.repo.write("notes.md", "old\u200bline\n;;; Generated with ChatGPT\n")
        self.repo.commit(f"Update notes\n\n{TRAILER}")
        code, found = self.findings("range", base)
        self.assertEqual(code, 1)
        self.assertEqual(
            sorted((f["rule"], f["path"], f["line"]) for f in found),
            [("ai-footer", "notes.md", 2), ("ai-trailer", None, 3)],
        )

    def test_binary_metadata(self):
        self.repo.write("img/logo.pdf", b"%PDF-1.7\n1 0 obj\n<< /Producer (ChatGPT) >>\nendobj\n")
        self.repo.commit("Add logo")
        _, found = self.findings("range", self.base)
        self.assertEqual([(f["rule"], f["path"]) for f in found], [("ai-metadata", "img/logo.pdf")])

    def test_ai_author(self):
        self.repo.write("a.txt", "a\n")
        self.repo.commit("Add a", author="Cursor Agent <cursoragent@cursor.com>")
        _, found = self.findings("range", self.base)
        self.assertEqual([f["rule"] for f in found], ["ai-identity"])


class HookTest(RepoTestCase):
    def test_staged(self):
        self.repo.write("lib/x.lisp", "(defun x () 1)\n")
        self.repo.git("add", "-A")
        self.assertEqual(self.findings("staged"), (0, []))
        self.repo.write("lib/x.lisp", "(defun x () 1)\n;; Author: Claude\n")
        self.repo.git("add", "-A")
        code, found = self.findings("staged")
        self.assertEqual((code, [(f["rule"], f["line"]) for f in found]), (1, [("ai-footer", 2)]))

    def test_commit_message_ignores_comments(self):
        path = os.path.join(self.repo.path, "MSG")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Fix bug\n\n# Co-Authored-By: Claude <noreply@anthropic.com>\n")
        self.assertEqual(self.findings("message", path), (0, []))
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Fix bug\n\n{TRAILER}\n")
        code, found = self.findings("message", path)
        self.assertEqual((code, [f["rule"] for f in found]), (1, ["ai-trailer"]))

    def test_tools_command_includes_project_entries(self):
        self.repo.write(".no-ai-marks.toml", '[[tool]]\nid = "acme"\nnames = ["Acme Coder"]\n')
        code, out, _ = self.repo.run("tools")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^claude\s+product\s+Claude")
        self.assertRegex(out, r"(?m)^acme\s+product\s+Acme Coder$")

    def test_text_output_format(self):
        path = os.path.join(self.repo.path, "MSG")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Fix bug\n\n{TRAILER}\n")
        code, out, _ = self.repo.run("message", path, "--format", "text")
        self.assertEqual(code, 1)
        self.assertIn("commit message, line 3: error: 'Co-Authored-By' trailer credits Claude", out)


class CiTest(RepoTestCase):
    def event(self, name, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        self.addCleanup(os.unlink, path)
        return {"GITHUB_EVENT_NAME": name, "GITHUB_EVENT_PATH": path}

    def pull_request(self, head, body="", title="Fix login", branch="claude/fix-login"):
        return self.event("pull_request", {"pull_request": {
            "title": title, "body": body,
            "base": {"sha": self.base, "ref": "main"},
            "head": {"sha": head, "ref": branch},
        }})

    def test_pull_request(self):
        self.repo.git("checkout", "-q", "-b", "claude/fix-login")
        self.repo.write("src/login.ts", "export const ok = true;\u200b\n")
        head = self.repo.commit(f"Fix login\n\n{TRAILER}")
        body = "Fixes the login bug.\n\n\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)"
        code, found = self.findings("ci", env=self.pull_request(head, body))
        self.assertEqual(code, 1)
        self.assertEqual(
            sorted((f["rule"], f["source"]) for f in found),
            [
                ("ai-branch", "branch claude/fix-login"),
                ("ai-emoji", "pull request body"),
                ("ai-footer", "pull request body"),
                ("ai-trailer", f"commit {head[:12]}"),
                ("invisible-char", "src/login.ts"),
            ],
        )

    def test_github_format_escapes_untrusted_text(self):
        self.repo.git("checkout", "-q", "-b", "topic")
        head = self.repo.commit(f"Innocent\n::error::injected\n{TRAILER}")
        code, out, _ = self.repo.run("ci", "--format", "github", env=self.pull_request(head, branch="topic"))
        self.assertEqual(code, 1)
        for line in out.splitlines():
            self.assertFalse(line.startswith("::error::injected"), line)
        self.assertIn("::error title=no-ai-marks ai-trailer::", out)

    def test_config_comes_from_the_base_commit(self):
        self.repo.write(".github/no-ai-marks.toml", '[rules]\nai-emoji = "off"\n')
        self.base = self.repo.commit("Add config")
        self.repo.git("checkout", "-q", "-b", "topic")
        # The pull request tries to switch the trailer rule off.
        self.repo.write(".github/no-ai-marks.toml", '[rules]\nai-emoji = "off"\nai-trailer = "off"\n')
        head = self.repo.commit(f"Loosen rules\n\n{TRAILER}")
        env = self.pull_request(head, body="\U0001F916", branch="topic")
        code, out, _ = self.repo.run("ci", "--format", "text", env=env)
        self.assertEqual(code, 1)
        self.assertIn("[ai-trailer]", out)
        self.assertNotIn("[ai-emoji]", out)
        self.assertIn("edits the no-ai-marks config", out)

    def test_push_of_new_branch(self):
        self.repo.git("checkout", "-q", "-b", "topic")
        self.repo.write("a.md", "Written by ChatGPT\n")
        head = self.repo.commit("Add a")
        env = self.event("push", {"ref": "refs/heads/topic", "before": "0" * 40, "after": head, "repository": {"default_branch": "main"}})
        code, found = self.findings("ci", env=env)
        self.assertEqual((code, [f["rule"] for f in found]), (1, ["ai-footer"]))

    def test_missing_history_is_explained(self):
        env = self.pull_request("f" * 40)
        code, _, err = self.repo.run("ci", "--format", "text", env=env)
        self.assertEqual(code, 2)
        self.assertIn("fetch-depth: 0", err)


if __name__ == "__main__":
    unittest.main()
