import os
import subprocess
import sys
import tempfile

from no_ai_marks.config import Config
from no_ai_marks.scan import Scanner

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin", "no-ai-marks")

# Keep the user's git config and hooks out of the test repositories.
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITHUB_"))}
ENV.update(
    GIT_CONFIG_GLOBAL=os.devnull,
    GIT_CONFIG_NOSYSTEM="1",
    GIT_AUTHOR_NAME="Jane Dev",
    GIT_AUTHOR_EMAIL="jane@example.com",
    GIT_COMMITTER_NAME="Jane Dev",
    GIT_COMMITTER_EMAIL="jane@example.com",
)


def scanner(cfg=None):
    return Scanner(cfg or Config())


def text_rules(text, cfg=None):
    s = scanner(cfg)
    s.text(text, "test")
    return [f.rule for f in s.findings]


def line_rules(line, path="src/example.txt", number=5, cfg=None):
    s = scanner(cfg)
    s.file_line(path, number, line)
    return [f.rule for f in s.findings]


class Repo:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = self._tmp.name
        self.git("init", "-q", "-b", "main")
        self.git("config", "commit.gpgsign", "false")

    def cleanup(self):
        self._tmp.cleanup()

    def git(self, *args):
        proc = subprocess.run(
            ["git", *args], cwd=self.path, env=ENV, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return proc.stdout.decode().strip()

    def write(self, name, content):
        full = os.path.join(self.path, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(full, mode, **({} if mode == "wb" else {"encoding": "utf-8", "newline": ""})) as f:
            f.write(content)

    def commit(self, message, author=None):
        self.git("add", "-A")
        args = ["commit", "-q", "--allow-empty", "-m", message]
        if author:
            args.append(f"--author={author}")
        self.git(*args)
        return self.git("rev-parse", "HEAD")

    def run(self, *args, env=None, input=None):
        proc = subprocess.run(
            [sys.executable, BIN, *args], cwd=self.path, env={**ENV, **(env or {})},
            input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")
