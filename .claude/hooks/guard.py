"""Claude Code hooks for this repo: `pre` blocks forbidden actions, `post` formats edited Python files."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import PurePath
from typing import Any

ALLOW_HELD_OUT_ENV = "CLAUDE_ALLOW_HELDOUT"
HELD_OUT_FILES = frozenset({f"T{n}.txt" for n in range(22, 31)} | {f"S{n:03d}.json" for n in range(43, 61)})
HELD_OUT_FILE_RE = re.compile(r"\b(?:T2[2-9]|T30)\.txt\b|\b(?:S04[3-9]|S05\d|S060)\.json\b", re.IGNORECASE)
HELD_OUT_ID_RE = re.compile(r"\b(?:T2[2-9]|T30|S04[3-9]|S05\d|S060)\b")
SERIES_DIR_RE = re.compile(r"data[\\/]+(?:bitacoras|snapshots)", re.IGNORECASE)
ENV_TOKEN_RE = re.compile(r"(?<![\w-])\.env(?:\.[\w-]+)*")
GIT_CMD_RE = re.compile(r"\bgit(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?))*\s+([a-z][\w-]*)([^;&|\n]*)")
GIT_WRITE_SUBCOMMANDS = frozenset(
    {
        "add", "am", "apply", "branch", "checkout", "cherry-pick", "clean", "commit", "init", "merge", "mv",
        "pull", "push", "rebase", "reset", "restore", "revert", "rm", "stash", "switch", "tag", "worktree",
    }
)  # fmt: skip
BRANCH_WRITE_FLAGS = frozenset(
    {
        "-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
        "-u", "--set-upstream-to", "--unset-upstream", "-t", "--track", "--edit-description",
    }
)  # fmt: skip
GIT_WRITE_REASON = (
    "Git write actions belong to the user: give them the exact commands instead of running them."
)
GITHUB_WRITE_RE = re.compile(
    r"\bgh\s+(?:pr\s+(?:create|merge|close|reopen|edit|ready|review|comment)"
    r"|release\s+(?:create|delete|edit|upload)|repo\s+(?:create|delete|fork|rename|edit|sync)"
    r"|issue\s+(?:create|close|reopen|edit|comment|delete))\b"
)
HELD_OUT_REASON = (
    "Days 8-10 are held out (FR-40): shifts T22-T30 and snapshots S043-S060 cannot be read before week 5. "
    "Use explicit files from days 1-7, or ask the user to set CLAUDE_ALLOW_HELDOUT=1."
)


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _is_env_file(path: str) -> bool:
    name = PurePath(_norm(path)).name
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def _in_z_helps(path: str) -> bool:
    return "z_helps" in PurePath(_norm(path)).parts


def _held_out_allowed() -> bool:
    return os.environ.get(ALLOW_HELD_OUT_ENV) == "1"


def _is_held_out_path(path: str) -> bool:
    norm = _norm(path)
    return bool(SERIES_DIR_RE.search(norm)) and PurePath(norm).name.upper() in {
        f.upper() for f in HELD_OUT_FILES
    }


def _covers_series_data(path: str) -> bool:
    norm = _norm(path).rstrip("/")
    return bool(SERIES_DIR_RE.search(norm)) or norm == "data" or norm.endswith("/data")


def expand_braces(pattern: str) -> list[str]:
    """Expand the first `{a,b}` group recursively so fnmatch can evaluate brace globs."""
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    head, tail = pattern[: match.start()], pattern[match.end() :]
    return [
        expanded for option in match.group(1).split(",") for expanded in expand_braces(head + option + tail)
    ]


def _glob_hits_held_out(glob: str) -> bool:
    patterns = expand_braces(PurePath(_norm(glob)).name)
    return any(fnmatch.fnmatchcase(name, p) for p in patterns for name in HELD_OUT_FILES)


def _git_read_only(subcommand: str, args: list[str]) -> bool:
    """Return True for the read-only forms of otherwise mutating git subcommands."""
    first = args[0] if args else ""
    if subcommand == "branch":
        return not BRANCH_WRITE_FLAGS.intersection(args) and (not args or first.startswith("-"))
    if subcommand in {"stash", "worktree"}:
        return first in {"list", "show"}
    if subcommand == "tag":
        return first in {"", "-l", "--list"}
    return False


def check_git_writes(command: str) -> str | None:
    if GITHUB_WRITE_RE.search(command):
        return "GitHub write actions belong to the user: give them the command, or use /pr-handoff for PRs."
    for match in GIT_CMD_RE.finditer(command):
        subcommand, args = match.group(1), match.group(2).split()
        if subcommand in GIT_WRITE_SUBCOMMANDS and not _git_read_only(subcommand, args):
            return f"{GIT_WRITE_REASON} Blocked: git {subcommand}."
    return None


def check_shell(command: str) -> str | None:
    if reason := check_git_writes(command):
        return reason
    if any(_is_env_file(token) for token in ENV_TOKEN_RE.findall(command)):
        return "Access to .env is blocked (secrets). Use .env.example or settings."
    if not _held_out_allowed():
        if HELD_OUT_FILE_RE.search(command):
            return HELD_OUT_REASON
        if SERIES_DIR_RE.search(command) and (
            HELD_OUT_ID_RE.search(command) or "*" in command or "glob" in command.lower()
        ):
            return HELD_OUT_REASON + " Wildcards over data/bitacoras or data/snapshots are not allowed."
    return None


def check_path(path: str) -> str | None:
    if _is_env_file(path):
        return "Access to .env is blocked (secrets). Use .env.example or settings."
    if not _held_out_allowed() and _is_held_out_path(path):
        return HELD_OUT_REASON
    return None


def check_grep(path: str, glob: str | None) -> str | None:
    if _is_env_file(path):
        return "Access to .env is blocked (secrets)."
    if _held_out_allowed() or not path:
        return None
    if _is_held_out_path(path):
        return HELD_OUT_REASON
    if _covers_series_data(path):
        if not glob:
            return HELD_OUT_REASON + " Add a glob limited to days 1-7, e.g. T{0[1-9],1[0-9],2[01]}.txt."
        if _glob_hits_held_out(glob):
            return HELD_OUT_REASON + f" The glob '{glob}' matches held-out files."
    return None


def evaluate_pre(payload: dict[str, Any]) -> str | None:
    """Return the reason to block the tool call, or None to let it through."""
    tool = str(payload.get("tool_name", ""))
    tool_input: dict[str, Any] = payload.get("tool_input") or {}
    if tool in {"Bash", "PowerShell"}:
        return check_shell(str(tool_input.get("command", "")))
    if tool in {"Read", "Edit", "Write", "NotebookEdit"}:
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        return check_path(path)
    if tool == "Grep":
        glob = tool_input.get("glob")
        return check_grep(str(tool_input.get("path", "")), str(glob) if glob else None)
    return None


def run_post(payload: dict[str, Any]) -> str | None:
    """Format and lint an edited .py file; return remaining lint errors, if any."""
    path = str((payload.get("tool_input") or {}).get("file_path", ""))
    if not path.endswith(".py") or _in_z_helps(path) or not os.path.isfile(path):
        return None
    subprocess.run(["uv", "run", "ruff", "format", path], capture_output=True, text=True, timeout=120)
    lint = subprocess.run(
        ["uv", "run", "ruff", "check", "--fix", path], capture_output=True, text=True, timeout=120
    )
    return lint.stdout.strip() or lint.stderr.strip() if lint.returncode != 0 else None


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "pre"
    try:
        payload = json.load(sys.stdin)
        message = evaluate_pre(payload) if mode == "pre" else run_post(payload)
    except Exception as exc:  # fail open: a broken guard must not freeze the session
        print(f"guard.py error ({mode}): {exc}", file=sys.stderr)
        return 1
    if message:
        print(f"Blocked by repo hook: {message}" if mode == "pre" else message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
