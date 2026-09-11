"""Configuration file loading."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field

from .model import RULES
from .patterns import Patterns, build as build_patterns
from .registry import Registry, RegistryError, default_registry, merged, validate

DEFAULT_PATHS = (".github/no-ai-marks.toml", ".no-ai-marks.toml")
SEVERITIES = ("error", "warning", "off")

_TOP_LEVEL = {"fail-on", "exclude", "disable-tools", "rules", "tool", "patterns", "unicode"}
_TABLES = {
    "patterns": {"extra", "extra-file"},
    "unicode": {"allow"},
}


class ConfigError(Exception):
    pass


def _default_severities() -> dict[str, str]:
    return {rule: severity for rule, (severity, _) in RULES.items()}


@dataclass
class Config:
    severities: dict = field(default_factory=_default_severities)
    fail_on: str = "error"
    exclude: list = field(default_factory=list)
    registry: Registry = field(default_factory=default_registry)
    extra_patterns: list = field(default_factory=list)
    extra_file_patterns: list = field(default_factory=list)
    allowed_chars: frozenset = frozenset()

    @property
    def patterns(self) -> Patterns:
        return build_patterns(self.registry)


def parse(text: str, source: str) -> Config:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{source}: {e}") from None

    def fail(message: str) -> ConfigError:
        return ConfigError(f"{source}: {message}")

    for key in data:
        if key not in _TOP_LEVEL:
            raise fail(f"unknown setting '{key}'")
    config = Config()

    fail_on = data.get("fail-on", "error")
    if fail_on not in ("error", "warning"):
        raise fail("fail-on must be 'error' or 'warning'")
    config.fail_on = fail_on
    config.exclude = _strings(data, "exclude", fail)

    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        raise fail("[rules] must be a table")
    for rule, severity in rules.items():
        if rule not in RULES:
            raise fail(f"unknown rule '{rule}' (known: {', '.join(RULES)})")
        if severity not in SEVERITIES:
            raise fail(f"rules.{rule} must be one of {', '.join(SEVERITIES)}")
        config.severities[rule] = severity

    try:
        entries = validate(data.get("tool", []))
        config.registry = Registry(merged(entries, _strings(data, "disable-tools", fail)))
    except RegistryError as e:
        raise fail(str(e)) from None

    tables = {}
    for name, keys in _TABLES.items():
        table = data.get(name, {})
        if not isinstance(table, dict):
            raise fail(f"[{name}] must be a table")
        for key in table:
            if key not in keys:
                raise fail(f"unknown setting '{name}.{key}'")
        tables[name] = table

    config.extra_patterns = _regexes(tables["patterns"], "extra", fail)
    config.extra_file_patterns = _regexes(tables["patterns"], "extra-file", fail)
    config.allowed_chars = frozenset(_code_point(v, fail) for v in _strings(tables["unicode"], "allow", fail))
    return config


def _strings(table: dict, key: str, fail) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise fail(f"{key} must be a list of strings")
    return value


def _regexes(table: dict, key: str, fail) -> list:
    compiled = []
    for pattern in _strings(table, key, fail):
        try:
            compiled.append(re.compile(pattern, re.I))
        except re.error as e:
            raise fail(f"{key}: bad regular expression {pattern!r}: {e}") from None
    return compiled


def _code_point(value: str, fail) -> int:
    """Accept "U+00A0", "00A0", or the character itself."""
    if len(value) == 1:
        return ord(value)
    digits = value[2:] if value.upper().startswith("U+") else value
    try:
        return int(digits, 16)
    except ValueError:
        raise fail(f"unicode.allow: '{value}' is not a code point like U+00A0") from None
