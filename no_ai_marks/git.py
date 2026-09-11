"""Thin wrappers around the git command line."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

NULL_SHA = "0" * 40
_GIT = ("git", "-c", "core.quotepath=off")
_HUNK = re.compile(rb"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_ESCAPE = re.compile(rb'\\([0-7]{3}|.)')
_ESCAPES = {b"a": b"\a", b"b": b"\b", b"f": b"\f", b"n": b"\n", b"r": b"\r", b"t": b"\t", b"v": b"\v"}
_LOG_FORMAT = "%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B"


class GitError(Exception):
    pass


def run(*args: str, check: bool = True, input: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            [*_GIT, *args],
            input=input,
            stdin=None if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise GitError("git is not installed or not on PATH") from None
    if check and proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return proc


def _text(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout.decode("utf-8", "replace").strip()


def _paths(raw: bytes) -> list[str]:
    return [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]


def resolve(rev: str) -> str | None:
    """The commit a revision names, or None if it isn't in the clone."""
    proc = run("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False)
    return _text(proc) if proc.returncode == 0 else None


def merge_base(a: str, b: str) -> str | None:
    proc = run("merge-base", a, b, check=False)
    return _text(proc) if proc.returncode == 0 else None


def empty_tree() -> str:
    return _text(run("hash-object", "-t", "tree", "--stdin", input=b""))


def diff_base(base: str | None, head: str) -> str:
    """What to diff head against: the merge base with base, or head's parent."""
    if base:
        return merge_base(base, head) or base
    return resolve(f"{head}^") or empty_tree()


def current_branch() -> str | None:
    proc = run("symbolic-ref", "--short", "--quiet", "HEAD", check=False)
    return _text(proc) if proc.returncode == 0 else None


@dataclass
class Commit:
    sha: str
    author_name: str
    author_email: str
    committer_name: str
    committer_email: str
    message: str


def commits(base: str | None, head: str) -> list[Commit]:
    """Commits in base..head, or just head when there is no base."""
    selection = [f"{base}..{head}"] if base else ["-1", head]
    raw = run("log", "-z", "--no-show-signature", f"--format={_LOG_FORMAT}", *selection, "--").stdout
    fields = [f.decode("utf-8", "replace") for f in raw.split(b"\0")]
    if len(fields) % 6 == 1 and fields[-1] == "":
        fields.pop()
    return [Commit(*fields[i:i + 6]) for i in range(0, len(fields) - 5, 6)]


def _diff_args(base: str | None, head: str | None, cached: bool) -> list[str]:
    return ["--cached"] if cached else [base, head]


def changed_files(base: str | None, head: str | None, *, cached: bool = False) -> list[str]:
    raw = run(
        "diff", "--name-only", "-z", "-M", "--diff-filter=ACMR", "--no-relative",
        *_diff_args(base, head, cached), "--",
    ).stdout
    return _paths(raw)


def _unquote(raw: bytes) -> bytes:
    def replace(m):
        code = m.group(1)
        if len(code) == 3:
            return bytes([int(code, 8)])
        return _ESCAPES.get(code, code)
    return _ESCAPE.sub(replace, raw[1:-1])


def added_lines(base: str | None, head: str | None, *, cached: bool = False) -> dict[str, list[tuple[int, str]]]:
    """Map each changed path to its added lines as (line number, text)."""
    raw = run(
        "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--no-relative", "-M", "-U0",
        "--diff-filter=ACMR", "--src-prefix=a/", "--dst-prefix=b/",
        *_diff_args(base, head, cached), "--",
    ).stdout
    result: dict[str, list[tuple[int, str]]] = {}
    lines = None
    in_hunk = False
    number = 0
    for row in raw.split(b"\n"):
        if row.startswith(b"diff --git "):
            in_hunk, lines = False, None
            continue
        if not in_hunk and row.startswith(b"+++ "):
            target = row[4:]
            if target.startswith(b'"'):
                target = _unquote(target)
            if target.startswith(b"b/"):
                lines = result.setdefault(target[2:].decode("utf-8", "surrogateescape"), [])
            continue
        m = _HUNK.match(row)
        if m:
            in_hunk, number = True, int(m.group(1))
            continue
        if in_hunk and lines is not None:
            if row.startswith(b"+"):
                lines.append((number, row[1:].decode("utf-8", "replace").rstrip("\r")))
                number += 1
            elif row.startswith(b" "):
                number += 1
    return result


def file_changed(base: str, head: str, path: str) -> bool:
    return run("diff", "--quiet", base, head, "--", path, check=False).returncode == 1


def show(rev: str, path: str) -> bytes | None:
    proc = run("cat-file", "blob", f"{rev}:{path}", check=False)
    return proc.stdout if proc.returncode == 0 else None


def ls_tree(rev: str) -> list[str]:
    return _paths(run("ls-tree", "-r", "-z", "--name-only", "--full-tree", rev).stdout)


def ls_files(paths=()) -> list[str]:
    """Tracked files, plus untracked files that aren't ignored."""
    return _paths(run("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *paths).stdout)


class Blobs:
    """Read many blobs through one `git cat-file --batch` process."""

    def __enter__(self) -> "Blobs":
        self._proc = subprocess.Popen(
            ["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        return self

    def __exit__(self, *exc) -> None:
        self._proc.stdin.close()
        self._proc.stdout.close()
        self._proc.wait()

    def read(self, spec: str) -> bytes | None:
        """Read "<rev>:<path>" (or ":<path>" for the index)."""
        self._proc.stdin.write(spec.encode("utf-8", "surrogateescape") + b"\n")
        self._proc.stdin.flush()
        header = self._proc.stdout.readline().split()
        if len(header) != 3:
            return None  # "<spec> missing" or "ambiguous"
        data = self._proc.stdout.read(int(header[2]))
        self._proc.stdout.read(1)
        return data if header[1] == b"blob" else None
