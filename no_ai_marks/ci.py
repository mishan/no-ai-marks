"""Work out what to scan from the GitHub Actions event."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import git


class EventError(Exception):
    pass


@dataclass
class Context:
    event: str
    base: str | None = None
    head: str | None = None
    branch: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    # Read the config from this commit instead of the working tree, so a
    # pull request can't loosen the rules it is checked against.
    trusted_rev: str | None = None
    notes: list = field(default_factory=list)


def context(env, base: str | None = None, head: str | None = None) -> Context:
    name = env.get("GITHUB_EVENT_NAME", "")
    path = env.get("GITHUB_EVENT_PATH", "")
    if not name or not path:
        raise EventError(
            "GITHUB_EVENT_NAME and GITHUB_EVENT_PATH are not set. Outside GitHub "
            "Actions, use the range, staged, message, or files commands."
        )
    with open(path, encoding="utf-8") as f:
        event = json.load(f)

    ctx = Context(event=name)
    if name in ("pull_request", "pull_request_target"):
        pr = event["pull_request"]
        ctx.base = pr["base"]["sha"]
        ctx.head = pr["head"]["sha"]
        ctx.branch = pr["head"]["ref"]
        ctx.pr_title = pr.get("title") or ""
        ctx.pr_body = pr.get("body") or ""
        ctx.trusted_rev = ctx.base
    elif name == "merge_group":
        group = event["merge_group"]
        ctx.base = group["base_sha"]
        ctx.head = group["head_sha"]
        ctx.trusted_rev = ctx.base
    elif name == "push":
        _push(event, ctx)
    else:
        ref = env.get("GITHUB_REF", "")
        if ref.startswith("refs/heads/"):
            ctx.branch = ref[len("refs/heads/"):]
        ctx.notes.append(
            f"The {name} event has no commit range, so only the branch name and "
            "(with scope: all) every tracked file are checked."
        )

    if base:
        ctx.base = base
    if head:
        ctx.head = head
    if ctx.base and not ctx.head:
        ctx.head = "HEAD"
    for rev in (ctx.base, ctx.head):
        if rev and not git.resolve(rev):
            hint = "Check out with actions/checkout and fetch-depth: 0."
            if name == "pull_request_target":
                hint += " With pull_request_target, also fetch the head: git fetch origin pull/<number>/head."
            raise EventError(f"commit {rev} is not in the local clone. {hint}")
    return ctx


def _push(event: dict, ctx: Context) -> None:
    ref = event.get("ref", "")
    if ref.startswith("refs/heads/"):
        ctx.branch = ref[len("refs/heads/"):]
    if event.get("deleted"):
        ctx.notes.append("The pushed ref was deleted; nothing to check.")
        return
    ctx.head = event.get("after")
    before = event.get("before") or ""
    if before and before != git.NULL_SHA and git.resolve(before):
        ctx.base = before
        return
    # A new branch (or a force push over history we don't have): compare
    # against the default branch.
    default = (event.get("repository") or {}).get("default_branch")
    if default and default != ctx.branch and ctx.head:
        ctx.base = git.merge_base(f"refs/remotes/origin/{default}", ctx.head)
    if not ctx.base:
        ctx.notes.append("No earlier commit to compare against; only the pushed head commit is checked.")
