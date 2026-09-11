"""Apply the rules to commit messages, pull request text, branch names, and
files."""

from __future__ import annotations

import fnmatch
import re
from collections import defaultdict

from . import chars, metadata, patterns
from .config import Config
from .model import Finding
from .registry import split_identity

# A file line containing this is skipped, for docs that must quote a marker.
ALLOW_MARKER = "no-ai-marks: allow"

_LIST_SEPARATOR = re.compile(r"\s*(?:,|&|\band\b)\s*", re.I)

_NOUNS = {
    "invisible-char": "invisible character",
    "unusual-space": "unusual space",
    "private-use": "private-use character",
}


def _search(line: str, *regexes):
    for regex in regexes:
        m = regex.search(line)
        if m:
            return m
    return None


def _span(m) -> tuple[str, int]:
    """The interesting part of a match and its 1-based column."""
    group = "core" if "core" in m.re.groupindex else 0
    return m.group(group).strip(), m.start(group) + 1


def _credited(message: str, tool: str | None) -> str:
    return f"{message} ({tool})" if tool else message


class Scanner:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.registry = config.registry
        self.patterns = config.patterns
        self.findings: list[Finding] = []
        self.counts = {"commits": 0, "files": 0}

    def add(self, rule: str, message: str, where: dict, *, column=None, line_text=None) -> None:
        severity = self.config.severities[rule]
        if severity == "off":
            return
        excerpt = chars.snippet(line_text, column) if line_text else ""
        self.findings.append(Finding(rule, severity, message, column=column, excerpt=excerpt, **where))

    def excluded(self, path: str) -> bool:
        for pattern in self.config.exclude:
            if fnmatch.fnmatchcase(path, pattern):
                return True
            if not any(c in pattern for c in "*?[") and path.startswith(pattern.rstrip("/") + "/"):
                return True
        return False

    def _footer(self, m, where: dict, line: str) -> None:
        found, column = _span(m)
        name = m.groupdict().get("name")
        tool = self.registry.tool_for_name(name, "phrases") if name else None
        message = _credited(f"credits an AI tool: '{chars.visible(found)}'", tool)
        self.add("ai-footer", message, where, column=column, line_text=line)

    # Commit messages, pull request text, branch names.

    def commit(self, commit) -> None:
        self.counts["commits"] += 1
        source = f"commit {commit.sha[:12]}"
        people = (
            ("author", commit.author_name, commit.author_email),
            ("committer", commit.committer_name, commit.committer_email),
        )
        for role, name, email in people:
            tool = self.registry.identify(name, email)
            if tool:
                self.add("ai-identity", f"{role} is {name} <{email}> ({tool})", {"source": source})
        self.text(commit.message, source)

    def text(self, text: str, source: str) -> None:
        """Scan a commit message or pull request title or body."""
        p = self.patterns
        for number, line in enumerate(text.split("\n"), 1):
            line = line.rstrip("\r")
            where = {"source": source, "line": number}
            if not self._trailer(line, where):
                m = _search(line, p.attribution, p.author_field, *self.config.extra_patterns)
                if m:
                    self._footer(m, where, line)
            m = self.registry.markers.search(line)
            if m:
                message = _credited(f"AI tool marker '{chars.visible(m.group(0))}'", self.registry.marker_tool(m.group(0)))
                self.add("ai-footer", message, where, column=m.start() + 1, line_text=line)
            m = p.ai_tag.search(line)
            if m:
                self.add("ai-tag", f"AI tag '{chars.visible(m.group(0).strip())}'", where, column=m.start() + 1, line_text=line)
            column = line.find(patterns.ROBOT)
            if column >= 0:
                self.add("ai-emoji", "robot emoji signature", where, column=column + 1, line_text=line)
            m = self.registry.session_links.search(line)
            if m:
                self.add("ai-session-link", f"links to an AI session: {m.group(0)}", where, column=m.start() + 1, line_text=line)
            self._chars(line, where)

    def _trailer(self, line: str, where: dict) -> bool:
        m = patterns.TRAILER.match(line)
        if not m:
            return False
        key, value = m.groups()
        tool_key = self.registry.trailer_keys.fullmatch(key)
        if patterns.AI_TRAILER_KEY.fullmatch(key) or tool_key:
            if value.strip().lower() in patterns.NEGATIVE_VALUES:
                return False
            tool = self.registry.tool_for_name(key.split("-", 1)[0], "identity") if tool_key else None
            self.add("ai-trailer", _credited(f"'{key}' trailer", tool), where, column=m.start(1) + 1, line_text=line)
            return True
        if patterns.CREDIT_KEY.fullmatch(key):
            tool = self._identify_list(value)
            if tool:
                message = f"'{key}' trailer credits {chars.visible(value.strip())} ({tool})"
                self.add("ai-trailer", message, where, column=m.start(1) + 1, line_text=line)
                return True
        return False

    def _identify_list(self, value: str) -> str | None:
        """The tool credited by a trailer value, which may list several
        people: "Jane Doe and Claude", "Jane <j@x>, Claude <...>"."""
        tool = self.registry.identify(*split_identity(value))
        if tool:
            return tool
        for part in _LIST_SEPARATOR.split(value):
            if part and part != value:
                tool = self.registry.identify(*split_identity(part))
                if tool:
                    return tool
        return None

    def branch(self, name: str) -> None:
        where = {"source": f"branch {name}"}
        prefix = name.split("/", 1)[0].lower() if "/" in name else None
        tool = self.registry.branch_prefixes.get(prefix) if prefix else None
        if tool:
            self.add("ai-branch", f"branch name starts with '{prefix}/' ({tool})", where)
        else:
            for regex, tool in self.registry.branch_patterns:
                if regex.match(name):
                    self.add("ai-branch", f"branch name matches '{regex.pattern}' ({tool})", where)
                    break
        self._chars(name, where)

    # Files.

    def file(self, path: str, data: bytes, added=None) -> None:
        """Scan one file. `added` is a list of (line number, text) to limit
        the text checks to those lines; None checks every line."""
        if self.excluded(path):
            return
        self.counts["files"] += 1
        if metadata.is_binary(data):
            for rule, message in metadata.scan_blob(data, self.registry):
                self.add(rule, message, {"source": path, "path": path})
            return
        if added is None:
            added = enumerate(data.decode("utf-8", "replace").split("\n"), 1)
        for number, line in added:
            self.file_line(path, number, line.rstrip("\r"))

    def file_line(self, path: str, number: int, line: str) -> None:
        if ALLOW_MARKER in line:
            return
        p = self.patterns
        where = {"source": path, "path": path, "line": number}
        m = _search(line, p.attribution, p.author_field, p.generator_field, *self.config.extra_file_patterns)
        if m:
            self._footer(m, where, line)
        m = self.registry.emails.search(line)
        if m:
            message = _credited(f"AI bot email {m.group(0)}", self.registry.identify("", m.group(0)))
            self.add("ai-identity", message, where, column=m.start() + 1, line_text=line)
        m = self.registry.session_links.search(line)
        if m:
            self.add("ai-session-link", f"links to an AI session: {m.group(0)}", where, column=m.start() + 1, line_text=line)
        m = patterns.TEXT_PROVENANCE.search(line)
        if m:
            self.add("ai-metadata", "IPTC digital source type marks it as AI-generated", where, column=m.start() + 1, line_text=line)
        self._chars(line, where, at_file_start=number == 1)

    def _chars(self, text: str, where: dict, *, at_file_start: bool = False) -> None:
        hits = defaultdict(list)
        for rule, column, cp in chars.scan(text, at_file_start=at_file_start, allowed=self.config.allowed_chars):
            hits[rule].append((column, cp))
        for rule, found in hits.items():
            names = list(dict.fromkeys(chars.describe(cp) for _, cp in found))
            count = len(found)
            message = f"{count} {_NOUNS[rule]}{'' if count == 1 else 's'}: {', '.join(names[:3])}"
            if len(names) > 3:
                message += ", ..."
            hidden = chars.hidden_text([cp for _, cp in found]) if rule == "invisible-char" else ""
            if hidden:
                message += f" (hidden text: '{chars.visible(hidden)}')"
            self.add(rule, message, where, column=found[0][0], line_text=text)
        for column, word, odd in chars.mixed_script_words(text):
            names = ", ".join(dict.fromkeys(chars.describe(cp) for cp in odd))
            self.add("homoglyph", f"'{chars.visible(word)}' mixes Latin with {names}", where, column=column, line_text=text)
