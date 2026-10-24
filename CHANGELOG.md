# Changelog

## 0.2.3 (2026-10-24)

A tracked file whose path contains a newline no longer hides itself and the
files read after it from the scan. Such a path split the batch read of file
contents, so every later read got the wrong file and the scan could pass
with marks in it. Thanks @Uddoo.
([#9](https://github.com/mishan/no-ai-marks/pull/9))

## 0.2.2 (2026-10-20)

A zero-width space directly after `@` in a commit message or pull request no
longer fails the check. That's how GitHub quotes a mention without notifying
anyone, and Dependabot puts one in every release note it quotes. A
zero-width space anywhere else, including after `@` in a file or branch
name, is still flagged. ([#7](https://github.com/mishan/no-ai-marks/pull/7))

## 0.2.1 (2026-10-17)

The first release on PyPI. What it checks is unchanged from 0.2.0.

Install the command line with `pipx install no-ai-marks`, or run it once
with `uvx no-ai-marks`. In a CI system other than GitHub Actions,
`pip install no-ai-marks` and run `no-ai-marks range BASE`.

## 0.2.0 (2026-10-17)

Credit that names no AI tool now warns instead of failing. Phrases whose
only name for the tool is a generic one, such as "an AI tool", report as
`ai-generic`, a new rule that defaults to warning. Set
`ai-generic = "error"` under `[rules]` to keep failing on them. Phrases
naming a tool ("Generated with Claude Code", "Written by ChatGPT") are
`ai-footer` errors as before.

The README and CONTRIBUTING now say where the project stands: it isn't an
anti-AI tool and doesn't block contributions that AI tools helped write,
only the attribution and hidden characters they carry.

## 0.1.1 (2026-09-11)

Fixes the setup snippets. The README, the example workflow, and the
reusable workflow still referred to `OWNER/no-ai-marks`, so copied snippets
failed and the reusable workflow couldn't run. The pre-commit snippet now
names this tag.

## 0.1 (2026-09-11)

Initial release.
