"""The AI tools the rules look for, and the lookups built from them.

The built-in list is data/tools.toml. A project's config file adds entries,
or extends built-in ones, with the same [[tool]] tables. Anything that
changes when a new model or agent ships belongs in that data, not in code.
"""

from __future__ import annotations

import functools
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

BUILTIN = Path(__file__).parent / "data" / "tools.toml"

KINDS = ("product", "vendor", "generic")
CONTEXTS = ("phrases", "tags", "identity", "metadata")
_KIND_CONTEXTS = {
    "product": frozenset(CONTEXTS),
    "vendor": frozenset({"phrases", "identity", "metadata"}),
    "generic": frozenset({"phrases"}),
}
_KIND_ORDER = {kind: i for i, kind in enumerate(KINDS)}

_STRING_FIELDS = frozenset({"id", "kind", "source"})
_BOOL_FIELDS = frozenset({"first-name"})
_LIST_FIELDS = frozenset({
    "names", "patterns", "models", "emails", "github-logins", "author-patterns",
    "branch-prefixes", "branch-patterns", "session-urls", "markers",
    "metadata-keys", "skip", "examples", "counterexamples",
})
_REGEX_FIELDS = ("patterns", "author-patterns", "branch-patterns")

_NEVER = "(?!)"
_SEP = r"(?:\s+|-)"
# Pages under a session URL prefix that aren't sessions.
_NOT_A_SESSION = r"(?!(?:new|new_chat|onboarding|settings|about|help|docs|login|install)(?![\w-]))"
# After a name that is also a first name, a capitalized word makes it a
# person: Claude Shannon, Claude-Henri Dupont.
_NOT_A_SURNAME = r"(?![\s-]+(?-i:[A-Z][a-z]))"
_ADDRESS = re.compile(r"^(.*?)\s*<([^<>]*)>\s*$")


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class Tool:
    id: str
    kind: str = "product"
    first_name: bool = False
    source: str = ""
    names: tuple = ()
    patterns: tuple = ()
    models: tuple = ()
    emails: tuple = ()
    github_logins: tuple = ()
    author_patterns: tuple = ()
    branch_prefixes: tuple = ()
    branch_patterns: tuple = ()
    session_urls: tuple = ()
    markers: tuple = ()
    metadata_keys: tuple = ()
    skip: tuple = ()
    examples: tuple = ()
    counterexamples: tuple = ()

    @classmethod
    def from_entry(cls, entry: dict) -> "Tool":
        return cls(**{
            key.replace("-", "_"): tuple(value) if isinstance(value, list) else value
            for key, value in entry.items()
        })

    @property
    def contexts(self) -> frozenset:
        return _KIND_CONTEXTS[self.kind] - set(self.skip)


def validate(entries) -> list[dict]:
    """Check [[tool]] tables and return them. Errors name the entry."""
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise RegistryError("tool must be an array of tables, written [[tool]]")
    seen = set()
    for number, entry in enumerate(entries, 1):
        tool_id = entry.get("id")
        if not isinstance(tool_id, str) or not tool_id:
            raise RegistryError(f"[[tool]] #{number} needs an id")
        label = f"tool '{tool_id}'"
        if tool_id in seen:
            raise RegistryError(f"{label} is defined twice")
        seen.add(tool_id)
        for key, value in entry.items():
            if key in _STRING_FIELDS:
                ok, expected = isinstance(value, str), "text"
            elif key in _BOOL_FIELDS:
                ok, expected = isinstance(value, bool), "true or false"
            elif key in _LIST_FIELDS:
                ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
                expected = "a list of strings"
            else:
                raise RegistryError(f"{label}: unknown field '{key}'")
            if not ok:
                raise RegistryError(f"{label}: {key} must be {expected}")
        if entry.get("kind", "product") not in KINDS:
            raise RegistryError(f"{label}: kind must be one of {', '.join(KINDS)}")
        if set(entry.get("skip", [])) - set(CONTEXTS):
            raise RegistryError(f"{label}: skip can only list {', '.join(CONTEXTS)}")
        for key in _REGEX_FIELDS:
            for pattern in entry.get(key, []):
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise RegistryError(f"{label}: bad regular expression in {key}: {pattern!r}: {e}") from None
    return entries


@functools.lru_cache(maxsize=None)
def _builtin() -> tuple:
    with open(BUILTIN, "rb") as f:
        data = tomllib.load(f)
    try:
        unknown = set(data) - {"tool"}
        if unknown:
            raise RegistryError(f"unknown setting(s): {', '.join(sorted(unknown))}")
        return tuple(validate(data.get("tool", [])))
    except RegistryError as e:
        raise RegistryError(f"{BUILTIN}: {e}") from None


def merged(extra=(), disable=()) -> list[Tool]:
    """The built-in tools, extended or added to by `extra` entries, minus
    the ids in `disable`. An entry whose id is already known extends that
    tool: its lists are appended and its other values replace the old ones."""
    entries = {entry["id"]: entry for entry in _builtin()}
    for entry in extra:
        old = entries.get(entry["id"])
        entries[entry["id"]] = _extend(old, entry) if old else entry
    unknown = set(disable) - set(entries)
    if unknown:
        raise RegistryError(f"disable-tools: unknown tool id(s): {', '.join(sorted(unknown))}")
    return [Tool.from_entry(e) for tool_id, e in entries.items() if tool_id not in disable]


def _extend(old: dict, new: dict) -> dict:
    result = dict(old)
    for key, value in new.items():
        result[key] = list(dict.fromkeys([*old.get(key, []), *value])) if key in _LIST_FIELDS else value
    return result


# Regular expressions built from the entries.

def _alternation(parts) -> str:
    parts = list(parts)
    return f"(?:{'|'.join(parts)})" if parts else _NEVER


def literal(name: str) -> str:
    """A name as a regex. Its words may be separated by spaces or a hyphen."""
    return _SEP.join(re.escape(word) for word in re.split(r"[\s-]+", name.strip()) if word)


def name_regex(tool: Tool) -> str:
    """The tool's name as it appears in running text."""
    names = sorted(tool.names, key=len, reverse=True)
    regex = _alternation([literal(n) for n in names] + [f"(?:{p})" for p in tool.patterns])
    if tool.models:
        models = _alternation(literal(m) for m in tool.models)
        regex += rf"(?:{_SEP}{models}(?:\s+[\d.]+)?)?"
    if tool.first_name:
        regex += _NOT_A_SURNAME
    return f"(?:{regex})"


def login_regex(tool: Tool) -> str:
    """The tool's GitHub accounts, as normalized author names."""
    return _alternation(re.escape(normalize_name(login)) for login in tool.github_logins)


def identity_regex(tool: Tool) -> str:
    """Matched against a whole author or trailer name, lowercased."""
    names = [literal(n) for n in tool.names] + [f"(?:{p})" for p in tool.patterns]
    parts = []
    if names:
        if tool.first_name:
            qualifiers = _alternation([
                *(literal(m) for m in tool.models), *names,
                "ai", "agent", "assistant", "bot", "chatbot", r"\d",
            ])
            parts.append(rf"{_alternation(names)}(?:[\s:(/-]+{qualifiers}(?!\w).*)?")
        else:
            parts.append(rf"{_alternation(names)}(?:(?!\w).*)?")
    parts += [f"(?:{p})" for p in tool.author_patterns]
    return _alternation(parts)


def email_regex(tool: Tool) -> str:
    parts = [re.escape(e).replace(r"\*", r"[\w.+-]*") for e in tool.emails]
    parts += [rf"(?:\d+\+)?{re.escape(login)}@users\.noreply\.github\.com" for login in tool.github_logins]
    return _alternation(parts)


def _url_regex(url: str) -> str:
    """A session URL prefix, followed by an id rather than an ordinary page."""
    return rf"(?<![\w.-])(?:[\w-]+\.)*{re.escape(url)}(?=[\w-]){_NOT_A_SESSION}"


def split_identity(value: str) -> tuple[str, str]:
    """Split "Name <email>" into its parts. A bare value is a name."""
    m = _ADDRESS.match(value.strip())
    return (m.group(1), m.group(2)) if m else (value.strip(), "")


def normalize_name(name: str) -> str:
    name = " ".join(name.strip().strip("\"'").split()).lower()
    return name[: -len("[bot]")] if name.endswith("[bot]") else name


class Registry:
    """Compiled lookups over a list of tools."""

    def __init__(self, tools: list[Tool]) -> None:
        # Products first, so a match is credited to the most specific tool.
        self.tools = sorted(tools, key=lambda t: _KIND_ORDER[t.kind])

        def names_in(context: str) -> str:
            return _alternation(name_regex(t) for t in self.tools if context in t.contexts)

        # Regex source, for patterns.py to put inside its phrases.
        self.phrase_names = names_in("phrases")
        self.tag_names = names_in("tags")
        self.metadata_names = re.compile(rf"(?<!\w){names_in('metadata')}(?!\w)", re.I)

        identity = [t for t in self.tools if "identity" in t.contexts]
        self.emails = re.compile(
            rf"(?<![\w.+-]){_alternation(email_regex(t) for t in identity)}(?![\w.-])", re.I,
        )
        self.session_links = re.compile(
            _alternation(_url_regex(u) for t in self.tools for u in t.session_urls), re.I,
        )
        # Trailer keys that start with a one-word tool name: Claude-Session.
        # Tools that skip short mentions ("tags") are left out, so a YAML
        # continue-on-error: line isn't taken for the Continue tool.
        words = [
            literal(n) for t in identity if "tags" in t.contexts
            for n in t.names if len(n.split()) == 1
        ]
        self.trailer_keys = re.compile(rf"{_alternation(words)}-[a-z][a-z0-9-]*", re.I)
        self.branch_prefixes = {p.lower().strip("/"): t.id for t in self.tools for p in t.branch_prefixes}
        self.branch_patterns = [(re.compile(p, re.I), t.id) for t in self.tools for p in t.branch_patterns]
        self.markers = re.compile(_alternation(re.escape(m) for t in self.tools for m in t.markers), re.I)
        self._marker_tools = {m.lower(): t.id for t in self.tools for m in t.markers}
        self.metadata_keys = {k.lower(): t.id for t in self.tools for k in t.metadata_keys}

        self._names = [(t, re.compile(name_regex(t), re.I)) for t in self.tools]
        self._identities = [
            (
                t.id,
                re.compile(login_regex(t), re.I),
                re.compile(email_regex(t), re.I),
                re.compile(identity_regex(t), re.I),
            )
            for t in identity
        ]

    def tool_for_name(self, text: str, context: str) -> str | None:
        """Which tool a matched name belongs to."""
        for tool, regex in self._names:
            if context in tool.contexts and regex.fullmatch(text):
                return tool.id
        return None

    def identify(self, name: str, email: str = "") -> str | None:
        """The tool an author name or email belongs to, if any."""
        name = normalize_name(name)
        email = email.strip().lower()
        # Exact accounts and addresses first, so chatgpt-codex-connector is
        # Codex rather than a name that starts with "ChatGPT".
        for tool_id, login, address, _ in self._identities:
            if (name and login.fullmatch(name)) or (email and address.fullmatch(email)):
                return tool_id
        for tool_id, _, _, names in self._identities:
            if name and names.fullmatch(name):
                return tool_id
        return None

    def marker_tool(self, text: str) -> str | None:
        return self._marker_tools.get(text.lower())


@functools.lru_cache(maxsize=None)
def default_registry() -> Registry:
    return Registry(merged())
