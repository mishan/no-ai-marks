# Contributing

## Adding or updating an AI tool

Most changes are data, not code. Every AI tool is an entry in
[no_ai_marks/data/tools.toml](no_ai_marks/data/tools.toml), and all the rules'
patterns are built from that file. The fields are described at the top of
it.

1. Find the tool's entry, or copy a similar one.
2. Add what changed. Common cases:
   - **A new model family** ("Claude Mythos"): add the word to `models`.
   - **A new bot account**: add it to `github-logins` (GitHub App accounts
     end in `[bot]`) or `emails`.
   - **An agent that creates branches**: add the prefix to `branch-prefixes`
     (`claude` for `claude/fix-login`). For names without a prefix, add a
     regular expression to `branch-patterns` (`Q-DEV-issue-\d+-\d+`).
   - **Shareable chat or session links**: add the URL prefix to
     `session-urls`, down to where the id starts
     (`claude.ai/code/session_`), so docs pages on the same host don't match.
   - **Fixed text the tool puts in pull request descriptions**, such as an
     HTML comment: add it to `markers`.
   - **A name that is also a first name** (Claude, Kimi): set
     `first-name = true`. For names that are too common to match alone
     (Devin, Jules), list only the qualified forms ("Devin AI").
   - **A name that is an ordinary word in some context**: leave that context
     out with `skip`. The Cursor entry skips `tags` because "(via cursor)"
     is ordinary talk in editor projects.
3. Add an `examples` string showing the marker exactly as the tool writes
   it. If the name could be mistaken for something ordinary, add a
   `counterexamples` string too.
4. Say where the details came from in `source`: the tool's source code,
   its docs, or public commits and pull requests. Leave "unverified" if you
   don't have one yet. Real examples are easy to find with the GitHub CLI:

   ```sh
   gh search commits "Co-Authored-By: Acme" --limit 5 --json url,commit
   gh search prs --author "app/acme-agent" --limit 5 --json url,title
   gh api repos/OWNER/REPO/pulls/N --jq '{branch: .head.ref, body: .body}'
   ```
5. Run the tests.

The tests check every example, counterexample, email, login, branch
prefix, session URL, marker, and metadata key in the file, so a new entry
is tested without writing test code.

[tests/corpus/](tests/corpus/) holds regression cases, one JSON object per
line: real commits, pull requests, and links the entries were checked
against, and the test cases of other projects that detect AI attribution
or hidden characters. A `pass` case with a note records a deliberate choice
not to flag something another project flags. When you fix a miss, add the
case there.

Projects don't have to wait for a release: the same `[[tool]]` entry works
in their own config file, and an entry with an existing id extends the
built-in one.

`no-ai-marks tools` prints the combined list a project ends up with.

## Adding a rule

1. Add the rule's id, default severity, and description to `RULES` in
   [no_ai_marks/model.py](no_ai_marks/model.py).
2. Detect it in [no_ai_marks/scan.py](no_ai_marks/scan.py): `text` for commit
   messages and pull request text, `file_line` for lines in files, and
   `file` for binary files.
3. Add tests and a row to the table in the README.

## Conventions

- Standard library only, Python 3.11 or newer.
- Every file stays ASCII. Write invisible or look-alike characters as
  escapes (`"\N{ZERO WIDTH SPACE}"`), so this repository passes its own
  check. CI runs the action on this repository.

## Running the tests

```sh
python3 -m unittest discover -s tests
```
