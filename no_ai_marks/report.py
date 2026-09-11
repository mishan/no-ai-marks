"""Print findings as plain text, GitHub workflow commands, or JSON."""

from __future__ import annotations

import json
from dataclasses import asdict

from .model import Finding


def counts(findings: list[Finding]) -> tuple[int, int]:
    errors = sum(f.severity == "error" for f in findings)
    return errors, len(findings) - errors


def exit_code(findings: list[Finding], fail_on: str) -> int:
    errors, warnings = counts(findings)
    return 1 if errors or (fail_on == "warning" and warnings) else 0


def _data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _property(text: str) -> str:
    return _data(text).replace(":", "%3A").replace(",", "%2C")


def github(findings: list[Finding]) -> list[str]:
    """Workflow commands. Everything taken from the repository is escaped
    so a crafted commit message can't inject commands of its own."""
    out = []
    for f in findings:
        props = [f"title={_property('no-ai-marks ' + f.rule)}"]
        message = f.message
        if f.path:
            props.insert(0, f"file={_property(f.path)}")
            if f.line:
                props.insert(1, f"line={f.line}")
                if f.column:
                    props.insert(2, f"col={f.column}")
        else:
            message = f"{f.where()}: {message}"
        if f.excerpt:
            message += f"\n    {f.excerpt}"
        out.append(f"::{f.severity} {','.join(props)}::{_data(message)}")
    return out


def text(findings: list[Finding]) -> list[str]:
    out = []
    for f in findings:
        out.append(f"{f.where()}: {f.severity}: {f.message} [{f.rule}]")
        if f.excerpt:
            out.append(f"    {f.excerpt}")
    return out


def as_json(findings: list[Finding]) -> str:
    return json.dumps([asdict(f) for f in findings], indent=2, ensure_ascii=True)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def summary_line(findings: list[Finding], scanned: dict) -> str:
    errors, warnings = counts(findings)
    parts = [_plural(n, word) for word, n in (("commit", scanned["commits"]), ("file", scanned["files"])) if n]
    checked = f"checked {' and '.join(parts)}" if parts else "checked"
    return f"no-ai-marks: {checked}: {_plural(errors, 'error')}, {_plural(warnings, 'warning')}"


def _code(text: str) -> str:
    """Table cell text inside a code span, where HTML can't take effect."""
    return text.replace("|", "\\|").replace("`", "'").replace("\n", " ")


def _cell(text: str) -> str:
    return _code(text).replace("<", "&lt;")


def markdown(findings: list[Finding], scanned: dict) -> str:
    lines = ["### no-ai-marks", "", summary_line(findings, scanned).split(": ", 1)[1], ""]
    if findings:
        lines += ["| Severity | Rule | Where | Finding |", "|---|---|---|---|"]
        for f in findings:
            detail = _cell(f.message)
            if f.excerpt:
                detail += f"<br>`{_code(f.excerpt)}`"
            lines.append(f"| {f.severity} | {f.rule} | {_cell(f.where())} | {detail} |")
    return "\n".join(lines) + "\n"
