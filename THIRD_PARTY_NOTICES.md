# Third-party notices

no-ai-marks is released under the [MIT License](LICENSE) and has no runtime
dependencies. This file covers material from other projects that the
repository includes or was built from.

## Regression corpus

[tests/corpus/](tests/corpus/) holds test cases used to compare no-ai-marks
with other projects. Every case has a `source` field saying where it came
from.

### Test inputs from MIT-licensed projects

Some cases reuse test inputs, fixture files, or tool output from these
projects, under the MIT License reproduced below with each project's
copyright notice.

| Project | Copyright notice | Used in the corpus |
|---|---|---|
| [dcondrey/unicode-safety-check](https://github.com/dcondrey/unicode-safety-check) | Copyright (c) 2026 David Condrey | Golden fixture files, CI and unit-test strings |
| [juriku/untrace](https://github.com/juriku/untrace) | Copyright (c) 2026 juriku | Test cases from `testdata/cases` |
| [juriku/hidden-characters-detector](https://github.com/juriku/hidden-characters-detector) | Copyright (c) 2025 juriku | Unit-test strings |
| [pixelstrunk/watermark-cleaner](https://github.com/pixelstrunk/watermark-cleaner) | Copyright (c) 2026 Christian Strunk | `tests/fixtures/parity/sample.md` and test strings |
| [cyzanfar/text-watermark-remover](https://github.com/cyzanfar/text-watermark-remover) | Copyright (c) 2026 Cyrus Anfar | Golden test cases and output of `eval/stego.py` |
| [flopp/invisible-characters](https://github.com/flopp/invisible-characters) | Copyright (c) 2022 Florian Pigorsch | Character list |
| [jaceddd/text_watermark](https://github.com/jaceddd/text_watermark) | Copyright (c) 2024 J Denby [Text watermark & Stegonography toolkit][rabian.io][4uracom@gmail.com] | Output of its encoder |
| [KuroLabs/stegcloak](https://github.com/KuroLabs/stegcloak) | Copyright (c) 2020 Jyothishmathi CV cvjyothishmathi@gmail.com  Kandavel A kanduarul@gmail.com, Mohanasundar M itsmohanpierce@gmail.com | `config-samples/out.txt` |
| [mplewis/no-ai-attribution](https://github.com/mplewis/no-ai-attribution) | Copyright (c) 2025 Matt Lewis | Unit-test strings |
| [ca1ebd/claude-attribution-guard](https://github.com/ca1ebd/claude-attribution-guard) | Copyright (c) 2026 Caleb Dudley | Cases built from its patterns |
| [AustinJiangH/drop-ai-coauthor](https://github.com/AustinJiangH/drop-ai-coauthor) | Copyright (c) 2026 | Cases built from its hook |

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Projects compared without copying their text

Cases credited to these projects contain only facts the projects list
(tool names, email addresses, code points), the lines AI tools themselves
write (such as commit trailers), output of running the tools on text
written for these tests, or strings written for these tests. No text
written by these projects is included.

| Project | License |
|---|---|
| [GoodHatsLLC/no-ai-coauthors](https://github.com/GoodHatsLLC/no-ai-coauthors) | none stated |
| [dalpat/git-strip-coauthor](https://github.com/dalpat/git-strip-coauthor) | none stated |
| [mherod's prepare-commit-msg gist](https://gist.github.com/mherod/e9edfb3102ffe19bb973643f077eaa26) | none stated |
| [Free-AI-Things/AI-DeWatermarker](https://github.com/Free-AI-Things/AI-DeWatermarker) | GPL-3.0 |
| [kilopal/GhostMark](https://github.com/kilopal/GhostMark) | Apache-2.0 |

### Real commits and pull requests

`hosted-agents.jsonl` and `cli-tools.jsonl` quote short lines that AI tools
write in public repositories: commit trailers, author lines, branch names,
pull request footers, and session links. They're evidence of each tool's
format. The tools generate this text; each case links the commit, pull
request, or documentation page it came from.

## Unicode data

The look-alike letter tables in [no_ai_marks/chars.py](no_ai_marks/chars.py)
were selected with the Unicode confusables data (`confusables.txt`, Unicode
Technical Standard #39), which is covered by this notice:

```
UNICODE LICENSE V3

COPYRIGHT AND PERMISSION NOTICE

Copyright (c) 1991-2026 Unicode, Inc.

NOTICE TO USER: Carefully read the following legal agreement. BY
DOWNLOADING, INSTALLING, COPYING OR OTHERWISE USING DATA FILES, AND/OR
SOFTWARE, YOU UNEQUIVOCALLY ACCEPT, AND AGREE TO BE BOUND BY, ALL OF THE
TERMS AND CONDITIONS OF THIS AGREEMENT. IF YOU DO NOT AGREE, DO NOT
DOWNLOAD, INSTALL, COPY, DISTRIBUTE OR USE THE DATA FILES OR SOFTWARE.

Permission is hereby granted, free of charge, to any person obtaining a
copy of data files and any associated documentation (the "Data Files") or
software and any associated documentation (the "Software") to deal in the
Data Files or Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, and/or sell
copies of the Data Files or Software, and to permit persons to whom the
Data Files or Software are furnished to do so, provided that either (a)
this copyright and permission notice appear with all copies of the Data
Files or Software, or (b) this copyright and permission notice appear in
associated Documentation.

THE DATA FILES AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF
THIRD PARTY RIGHTS.

IN NO EVENT SHALL THE COPYRIGHT HOLDER OR HOLDERS INCLUDED IN THIS NOTICE
BE LIABLE FOR ANY CLAIM, OR ANY SPECIAL INDIRECT OR CONSEQUENTIAL DAMAGES,
OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THE DATA
FILES OR SOFTWARE.

Except as contained in this notice, the name of a copyright holder shall
not be used in advertising or otherwise to promote the sale, use or other
dealings in these Data Files or Software without prior written
authorization of the copyright holder.
```
