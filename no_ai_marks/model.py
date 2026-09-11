"""Rules and findings."""

from __future__ import annotations

from dataclasses import dataclass

# Rule id -> (default severity, description).
RULES = {
    "ai-trailer": ("error", "Commit trailer credits an AI tool (Co-authored-by, Assisted-by, AI-*)"),
    "ai-identity": ("error", "Author, committer, or an email in a file is an AI tool's bot identity"),
    "ai-footer": ("error", "Attribution line such as 'Generated with ...' or 'Author: ChatGPT'"),
    "ai-tag": ("error", "AI tag such as [AI], (AI-generated), or '(via Claude)'"),
    "ai-emoji": ("error", "Robot emoji in a commit message or pull request"),
    "ai-session-link": ("error", "Link to an AI chat or agent session"),
    "ai-branch": ("error", "Branch name starts with an AI tool prefix such as claude/"),
    "ai-metadata": ("error", "File metadata marks the file as AI-generated or names an AI tool"),
    "c2pa-manifest": ("warning", "File embeds a C2PA content credentials manifest"),
    "invisible-char": ("error", "Zero-width, bidi control, tag, variation selector, or other invisible character"),
    "homoglyph": ("error", "Word mixes Latin letters with look-alike letters from another script"),
    "unusual-space": ("warning", "Space character other than U+0020"),
    "private-use": ("warning", "Private Use Area code point"),
}


@dataclass
class Finding:
    rule: str
    severity: str
    message: str
    source: str  # "commit 1a2b3c4d5e6f", "pull request body", "branch x", or a path
    path: str | None = None
    line: int | None = None
    column: int | None = None
    excerpt: str = ""

    def where(self) -> str:
        if self.path:
            loc = self.path
            if self.line:
                loc += f":{self.line}"
                if self.column:
                    loc += f":{self.column}"
            return loc
        return f"{self.source}, line {self.line}" if self.line else self.source
