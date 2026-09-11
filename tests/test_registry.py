import os
import re
import unittest

from helpers import ROOT, scanner
from test_metadata import chunk, png

from no_ai_marks.config import ConfigError, parse
from no_ai_marks.registry import default_registry

TOOLS = default_registry().tools


def findings(text, cfg=None):
    s = scanner(cfg)
    s.text(text, "example")
    return s.findings


class BuiltinToolsTest(unittest.TestCase):
    """Checks every entry in no_ai_marks/data/tools.toml."""

    def test_examples_are_flagged(self):
        for tool in TOOLS:
            for example in tool.examples:
                with self.subTest(tool=tool.id, example=example):
                    self.assertTrue(findings(example), "not flagged")

    def test_counterexamples_pass(self):
        for tool in TOOLS:
            for text in tool.counterexamples:
                with self.subTest(tool=tool.id, text=text):
                    self.assertEqual([f.message for f in findings(text)], [])

    def test_named_tools_have_examples(self):
        for tool in TOOLS:
            if tool.names or tool.patterns:
                with self.subTest(tool=tool.id):
                    self.assertTrue(tool.examples, "add an example")

    def test_emails_and_logins(self):
        for tool in TOOLS:
            addresses = [e.replace("*", "someone") for e in tool.emails]
            addresses += [f"12345+{login}@users.noreply.github.com" for login in tool.github_logins]
            for address in addresses:
                with self.subTest(tool=tool.id, address=address):
                    rules = [f.rule for f in findings(f"Co-authored-by: Someone <{address}>")]
                    self.assertIn("ai-trailer", rules)

    def test_branch_prefixes(self):
        for tool in TOOLS:
            for prefix in tool.branch_prefixes:
                with self.subTest(tool=tool.id, prefix=prefix):
                    s = scanner()
                    s.branch(f"{prefix}/topic")
                    self.assertEqual([f.rule for f in s.findings], ["ai-branch"])

    def test_session_urls(self):
        for tool in TOOLS:
            for url in tool.session_urls:
                with self.subTest(tool=tool.id, url=url):
                    rules = [f.rule for f in findings(f"See https://{url}abc123")]
                    self.assertEqual(rules, ["ai-session-link"])

    def test_markers(self):
        for tool in TOOLS:
            for marker in tool.markers:
                with self.subTest(tool=tool.id, marker=marker):
                    rules = [f.rule for f in findings(f"Some description. {marker} More text.")]
                    self.assertIn("ai-footer", rules)

    def test_metadata_keys(self):
        for tool in TOOLS:
            for key in tool.metadata_keys:
                with self.subTest(tool=tool.id, key=key):
                    s = scanner()
                    s.file("image.png", png(chunk(b"tEXt", key.encode() + b"\0value")))
                    self.assertEqual([f.rule for f in s.findings], ["ai-metadata"])


class ProjectToolsTest(unittest.TestCase):
    """[[tool]] entries in a project's config file."""

    def test_new_tool(self):
        cfg = parse('[[tool]]\nid = "acme"\nnames = ["Acme Coder"]\nbranch-prefixes = ["acme"]\n', "test.toml")
        self.assertEqual(findings("Generated with Acme Coder"), [])
        self.assertIn("(acme)", findings("Generated with Acme Coder", cfg)[0].message)
        s = scanner(cfg)
        s.branch("acme/topic")
        self.assertEqual([f.rule for f in s.findings], ["ai-branch"])

    def test_extending_a_builtin_tool(self):
        text = "Written by Claude Mythos"
        self.assertEqual(findings(text), [])
        cfg = parse('[[tool]]\nid = "claude"\nmodels = ["Mythos"]\n', "test.toml")
        self.assertTrue(findings(text, cfg))
        # The rest of the built-in entry is still there.
        self.assertTrue(findings("Co-Authored-By: Claude <noreply@anthropic.com>", cfg))

    def test_disabling_a_builtin_tool(self):
        cfg = parse('disable-tools = ["cursor"]\n', "test.toml")
        s = scanner(cfg)
        s.branch("cursor/topic")
        self.assertEqual(s.findings, [])

    def test_patterns_keep_their_spaces(self):
        # The grammar is compiled in verbose mode; user patterns must not be.
        cfg = parse("[[tool]]\nid = \"acme\"\npatterns = ['acme bot \\d+']\n", "test.toml")
        self.assertTrue(findings("Generated with Acme Bot 9", cfg))
        self.assertEqual(findings("Generated with acmebot9", cfg), [])

    def test_errors_name_the_entry(self):
        cases = [
            ('[[tool]]\nnames = ["x"]\n', "[[tool]] #1 needs an id"),
            ('[[tool]]\nid = "x"\nname = ["x"]\n', "tool 'x': unknown field 'name'"),
            ('[[tool]]\nid = "x"\nnames = "x"\n', "tool 'x': names must be a list of strings"),
            ("[[tool]]\nid = \"x\"\npatterns = ['(']\n", "tool 'x': bad regular expression in patterns"),
            ('[[tool]]\nid = "x"\nkind = "robot"\n', "tool 'x': kind must be one of"),
            ('[[tool]]\nid = "x"\nskip = ["files"]\n', "tool 'x': skip can only list"),
            ('[tool]\nid = "x"\n', "written [[tool]]"),
            ('disable-tools = ["nope"]\n', "unknown tool id(s): nope"),
        ]
        for text, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ConfigError, "^test.toml: .*" + re.escape(message)):
                    parse(text, "test.toml")

    def test_example_config_parses(self):
        with open(os.path.join(ROOT, "examples", "no-ai-marks.toml"), encoding="utf-8") as f:
            cfg = parse(f.read(), "examples/no-ai-marks.toml")
        self.assertIn("acme", cfg.registry.branch_prefixes)
        self.assertNotIn("cursor", cfg.registry.branch_prefixes)


if __name__ == "__main__":
    unittest.main()
