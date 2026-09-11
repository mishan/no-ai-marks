"""Command line entry point."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

from . import __version__, ci, config, git, report
from .model import RULES
from .registry import RegistryError
from .scan import Scanner

CHECKS = ("commits", "pr", "branch", "files")


def main(argv: list[str] | None = None) -> int:
    _use_utf8()
    args = _parser().parse_args(argv)
    args.format = args.format or ("github" if os.environ.get("GITHUB_ACTIONS") == "true" else "text")
    try:
        return args.func(args)
    except (config.ConfigError, RegistryError, git.GitError, ci.EventError, OSError) as e:
        if args.format == "github":
            print(f"::error title=no-ai-marks::{report._data(str(e))}")
        else:
            print(f"no-ai-marks: {e}", file=sys.stderr)
        return 2


def _use_utf8() -> None:
    """Read and write UTF-8 on every platform. On Windows, pipes otherwise
    use the ANSI code page: a finding that names a look-alike letter can't
    be printed, and a pull request body piped to `text` is misread."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="", help=f"config file (default: {' or '.join(config.DEFAULT_PATHS)})")
    common.add_argument("--format", choices=("text", "github", "json"), help="output format (default: github inside GitHub Actions, else text)")
    common.add_argument("--fail-on", choices=("error", "warning"), help="lowest severity that fails (overrides the config file)")
    common.add_argument("--report", metavar="PATH", help="also write findings to PATH as JSON")

    parser = argparse.ArgumentParser(prog="no-ai-marks", description="Find AI attribution and hidden watermarks.")
    parser.add_argument("--version", action="version", version=f"no-ai-marks {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ci", parents=[common], help="check what a GitHub Actions event changed")
    p.add_argument("--checks", default=",".join(CHECKS), help="comma-separated: " + ", ".join(CHECKS))
    p.add_argument("--scope", choices=("changed", "all"), default="changed", help="files: only added lines, or every tracked file")
    p.add_argument("--base", default="", help="override the base commit")
    p.add_argument("--head", default="", help="override the head commit")
    p.set_defaults(func=cmd_ci)

    p = sub.add_parser("range", parents=[common], help="check commits and added lines in BASE..HEAD")
    p.add_argument("base")
    p.add_argument("head", nargs="?", default="HEAD")
    p.set_defaults(func=cmd_range)

    p = sub.add_parser("staged", parents=[common], help="check lines staged for commit (pre-commit hook)")
    p.set_defaults(func=cmd_staged)

    p = sub.add_parser("message", parents=[common], help="check a commit message file (commit-msg hook)")
    p.add_argument("file")
    p.set_defaults(func=cmd_message)

    p = sub.add_parser("files", parents=[common], help="check whole files (default: every tracked file)")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_files)

    p = sub.add_parser("text", parents=[common], help="check text from FILE or stdin, e.g. a PR body")
    p.add_argument("file", nargs="?")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("branch", parents=[common], help="check a branch name (default: the current branch)")
    p.add_argument("name", nargs="?")
    p.set_defaults(func=cmd_branch)

    p = sub.add_parser("rules", help="list rules and their default severities")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("tools", parents=[common], help="list the AI tools the rules look for, after the config file")
    p.set_defaults(func=cmd_tools)
    return parser


def _load_config(path: str, rev: str | None = None) -> tuple[config.Config, str | None]:
    """Load the config from the working tree, or from commit `rev`. Returns
    the config and the path it came from."""
    for candidate in [path] if path else config.DEFAULT_PATHS:
        if rev:
            data = git.show(rev, candidate)
        elif os.path.isfile(candidate):
            with open(candidate, "rb") as f:
                data = f.read()
        else:
            data = None
        if data is not None:
            return config.parse(data.decode("utf-8"), candidate), candidate
    if path and not rev:
        raise config.ConfigError(f"{path}: no such file")
    return config.Config(), None


def scan_diff(scanner: Scanner, base: str | None, head: str | None, *, cached: bool = False) -> None:
    """Scan files changed between two commits, or staged in the index."""
    lines = git.added_lines(base, head, cached=cached)
    rev = "" if cached else head
    with git.Blobs() as blobs:
        for path in git.changed_files(base, head, cached=cached):
            if scanner.excluded(path):
                continue
            data = blobs.read(f"{rev}:{path}")
            if data is not None:
                scanner.file(path, data, lines.get(path, []))


def scan_tree(scanner: Scanner, rev: str) -> None:
    with git.Blobs() as blobs:
        for path in git.ls_tree(rev):
            if not scanner.excluded(path):
                data = blobs.read(f"{rev}:{path}")
                if data is not None:
                    scanner.file(path, data)


def _finish(scanner: Scanner, args, cfg: config.Config, notes=()) -> int:
    findings = scanner.findings
    if args.format == "json":
        print(report.as_json(findings))
    else:
        for note in notes:
            print(f"::notice title=no-ai-marks::{report._data(note)}" if args.format == "github" else f"note: {note}")
        lines = report.github(findings) if args.format == "github" else report.text(findings)
        for line in lines:
            print(line)
    print(report.summary_line(findings, scanner.counts), file=sys.stderr if args.format == "json" else sys.stdout)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report.as_json(findings))
    return report.exit_code(findings, args.fail_on or cfg.fail_on)


def cmd_ci(args) -> int:
    checks = {c.strip() for c in args.checks.split(",") if c.strip()}
    unknown = checks - set(CHECKS)
    if unknown:
        raise config.ConfigError(f"unknown checks: {', '.join(sorted(unknown))} (known: {', '.join(CHECKS)})")
    ctx = ci.context(os.environ, base=args.base or None, head=args.head or None)
    cfg, cfg_path = _load_config(args.config, ctx.trusted_rev)
    scanner = Scanner(cfg)
    notes = list(ctx.notes)

    if "branch" in checks and ctx.branch:
        scanner.branch(ctx.branch)
    if "pr" in checks and ctx.pr_title is not None:
        scanner.text(ctx.pr_title, "pull request title")
        scanner.text(ctx.pr_body, "pull request body")
    if ctx.head:
        if "commits" in checks:
            for commit in git.commits(ctx.base, ctx.head):
                scanner.commit(commit)
        diff_base = git.diff_base(ctx.base, ctx.head)
        if "files" in checks:
            if args.scope == "all":
                scan_tree(scanner, ctx.head)
            else:
                scan_diff(scanner, diff_base, ctx.head)
        watched = [args.config] if args.config else list(config.DEFAULT_PATHS)
        if ctx.trusted_rev and any(git.file_changed(diff_base, ctx.head, p) for p in watched):
            notes.append(
                f"This change edits the no-ai-marks config. The version from the base commit "
                f"{ctx.trusted_rev[:12]} was used; the edit takes effect after merge."
            )
    elif "files" in checks and args.scope == "all":
        scan_tree(scanner, "HEAD")

    code = _finish(scanner, args, cfg, notes)
    _publish(scanner, args)
    return code


def _publish(scanner: Scanner, args) -> None:
    """Write step outputs and the job summary when running in Actions."""
    errors, warnings = report.counts(scanner.findings)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"errors={errors}\nwarnings={warnings}\n")
            if args.report:
                f.write(f"report={args.report}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report.markdown(scanner.findings, scanner.counts))


def cmd_range(args) -> int:
    cfg, _ = _load_config(args.config)
    scanner = Scanner(cfg)
    for commit in git.commits(args.base, args.head):
        scanner.commit(commit)
    scan_diff(scanner, git.diff_base(args.base, args.head), args.head)
    return _finish(scanner, args, cfg)


def cmd_staged(args) -> int:
    cfg, _ = _load_config(args.config)
    scanner = Scanner(cfg)
    scan_diff(scanner, None, None, cached=True)
    return _finish(scanner, args, cfg)


def cmd_message(args) -> int:
    cfg, _ = _load_config(args.config)
    scanner = Scanner(cfg)
    with open(args.file, encoding="utf-8", errors="replace") as f:
        scanner.text(strip_git_comments(f.read()), "commit message")
    return _finish(scanner, args, cfg)


def strip_git_comments(raw: str) -> str:
    """A commit message file as git records it: without # comment lines or
    anything below the scissors line."""
    kept = []
    for line in raw.split("\n"):
        if line.startswith("# ------------------------ >8 ------------------------"):
            break
        if not line.startswith("#"):
            kept.append(line)
    return "\n".join(kept)


def cmd_files(args) -> int:
    cfg, _ = _load_config(args.config)
    scanner = Scanner(cfg)
    for path in _file_list(args.paths):
        if os.path.isfile(path):
            with open(path, "rb") as f:
                scanner.file(os.path.normpath(path).replace(os.sep, "/"), f.read())
    return _finish(scanner, args, cfg)


def _file_list(paths: list[str]) -> list[str]:
    """Files under `paths` (default: the whole repository) that git doesn't
    ignore, plus any file named explicitly. Outside a git repository, walk
    the directories instead."""
    explicit = [p for p in paths if os.path.isfile(p)]
    try:
        listed = git.ls_files(paths)
    except git.GitError:
        if not paths:
            raise
        listed = []
        for path in paths:
            for root, dirs, names in os.walk(path):
                dirs[:] = [d for d in dirs if d != ".git"]
                listed += [os.path.join(root, n) for n in names]
    return list(dict.fromkeys(listed + explicit))


def cmd_text(args) -> int:
    cfg, _ = _load_config(args.config)
    scanner = Scanner(cfg)
    if args.file:
        with open(args.file, encoding="utf-8", errors="replace") as f:
            scanner.text(f.read(), args.file)
    else:
        scanner.text(sys.stdin.read(), "stdin")
    return _finish(scanner, args, cfg)


def cmd_branch(args) -> int:
    cfg, _ = _load_config(args.config)
    scanner = Scanner(cfg)
    name = args.name or git.current_branch()
    if name:
        scanner.branch(name)
    return _finish(scanner, args, cfg)


def cmd_rules(args) -> int:
    width = max(map(len, RULES))
    for rule, (severity, description) in RULES.items():
        print(f"{rule:<{width}}  {severity:<7}  {description}")
    return 0


def cmd_tools(args) -> int:
    cfg, _ = _load_config(args.config)
    tools = cfg.registry.tools
    if args.format == "json":
        print(json.dumps([dataclasses.asdict(t) for t in tools], indent=2))
        return 0
    width = max((len(t.id) for t in tools), default=0)
    for t in tools:
        print(f"{t.id:<{width}}  {t.kind:<7}  {', '.join(t.names + t.patterns) or '-'}")
    print(f"{len(tools)} tools")
    return 0


if __name__ == "__main__":
    sys.exit(main())
