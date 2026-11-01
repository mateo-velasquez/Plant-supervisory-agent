"""Tests for the Claude Code repo hooks in .claude/hooks/guard.py."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

GUARD_PATH = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "guard.py"


def _load_guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("guard", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


@pytest.fixture(autouse=True)
def _held_out_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_ALLOW_HELDOUT", raising=False)


def _pre(tool: str, **tool_input: Any) -> str | None:
    result: str | None = guard.evaluate_pre({"tool_name": tool, "tool_input": tool_input})
    return result


@pytest.mark.parametrize(
    "command",
    [
        "git merge main",
        "git switch main; git merge feat/x",
        "gh pr create --fill",
        "gh pr merge 3 --squash",
        "gh pr close 3",
        "gh release create v1",
        "gh repo delete x",
        "git push --force",
        "git push -u origin chore/x",
        "git commit -m 'docs: x'",
        "git -C repo commit -am x",
        "git status --short; git commit -am x",
        "git add .",
        "git switch -c feat/y",
        "git checkout -b feat/y",
        "git checkout -- README.md",
        "git branch feat/y",
        "git branch -D old",
        "git stash",
        "git stash pop",
        "git reset --hard",
        "git rebase main",
        "git restore README.md",
        "git tag v1",
        "git pull",
    ],
)
def test_git_writes_block(command: str) -> None:
    assert _pre("Bash", command=command)
    assert _pre("PowerShell", command=command)


@pytest.mark.parametrize(
    "command",
    [
        "git merge-base main HEAD",
        "gh pr view 3",
        "git log --merges",
        "git log --oneline main..HEAD",
        "git status --short",
        "git diff main...HEAD",
        "git show HEAD",
        "git fetch origin",
        "git -C repo status",
        "git branch",
        "git branch -a",
        "git branch --show-current",
        "git stash list",
        "git stash show -p",
        "git tag",
        "git tag --list",
        "git worktree list",
    ],
)
def test_git_read_only_allowed(command: str) -> None:
    assert _pre("Bash", command=command) is None
    assert _pre("PowerShell", command=command) is None


@pytest.mark.parametrize(
    "path",
    [
        "data/bitacoras/T22.txt",
        r"C:\repo\data\bitacoras\T30.txt",
        "data/snapshots/S043.json",
        "data/snapshots/s060.json",
    ],
)
def test_held_out_paths_block(path: str) -> None:
    assert _pre("Read", file_path=path)


@pytest.mark.parametrize(
    "path", ["data/bitacoras/T21.txt", "data/snapshots/S042.json", "tests/fixtures/S043.json"]
)
def test_days_1_to_7_paths_allow(path: str) -> None:
    assert _pre("Read", file_path=path) is None


@pytest.mark.parametrize(
    "command",
    [
        r"Get-Content data\bitacoras\T22.txt",
        "cat data/snapshots/S050.json",
        "uv run python -c \"glob.glob('data/snapshots/S*.json')\"",
        r"Get-ChildItem data\bitacoras\*.txt | Get-Content",
    ],
)
def test_held_out_shell_block(command: str) -> None:
    assert _pre("PowerShell", command=command)


def test_listing_series_dir_without_wildcard_allowed() -> None:
    assert _pre("PowerShell", command=r"Get-ChildItem data\snapshots | Select-Object -First 5") is None


@pytest.mark.parametrize(
    ("path", "glob", "blocked"),
    [
        ("data/bitacoras", None, True),
        ("data", None, True),
        ("data/bitacoras", "*.txt", True),
        ("data/bitacoras", "T2*.txt", True),
        ("data/bitacoras", "T{2[2-9],30}.txt", True),
        ("data/bitacoras", "T{0[1-9],1[0-9],2[01]}.txt", False),
        ("data/bitacoras", "T0*.txt", False),
        ("src", None, False),
    ],
)
def test_grep_scope(path: str, glob: str | None, blocked: bool) -> None:
    assert bool(_pre("Grep", pattern="parada", path=path, glob=glob)) is blocked


def test_held_out_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_ALLOW_HELDOUT", "1")
    assert _pre("Read", file_path="data/bitacoras/T25.txt") is None
    assert _pre("Grep", pattern="x", path="data/bitacoras") is None


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": ".env"}),
        ("Edit", {"file_path": r"C:\repo\.env"}),
        ("Read", {"file_path": ".env.local"}),
        ("PowerShell", {"command": "Get-Content .env"}),
        ("Bash", {"command": "cat ./.env"}),
        ("Grep", {"pattern": "KEY", "path": ".env"}),
    ],
)
def test_env_blocked(tool: str, tool_input: dict[str, Any]) -> None:
    assert _pre(tool, **tool_input)


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": ".env.example"}),
        ("PowerShell", {"command": r".venv\Scripts\python -V"}),
        ("Bash", {"command": "cat .env.example"}),
    ],
)
def test_env_lookalikes_allowed(tool: str, tool_input: dict[str, Any]) -> None:
    assert _pre(tool, **tool_input) is None


def test_z_helps_is_read_write() -> None:
    assert _pre("Write", file_path="z_helps/notes.md") is None
    assert _pre("Edit", file_path=r"C:\repo\z_helps\x.md") is None
    assert _pre("PowerShell", command=r"Copy-Item notes.md z_helps\notes.md") is None
    assert _pre("Read", file_path="z_helps/Proyecto_Final_Monitoreo_en_planta.md") is None
    assert _pre("PowerShell", command=r"Get-Content z_helps\a.md") is None


def test_other_tools_pass_through() -> None:
    assert _pre("Glob", pattern="data/bitacoras/*.txt") is None


def _run_script(mode: str, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD_PATH), mode],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_script_blocks_with_exit_2_and_reason() -> None:
    result = _run_script("pre", {"tool_name": "Bash", "tool_input": {"command": "git merge main"}})
    assert result.returncode == 2
    assert "belong to the user" in result.stderr


def test_script_allows_with_exit_0() -> None:
    result = _run_script("pre", {"tool_name": "Bash", "tool_input": {"command": "git status"}})
    assert result.returncode == 0


def test_script_fails_open_on_bad_input() -> None:
    result = subprocess.run(
        [sys.executable, str(GUARD_PATH), "pre"],
        input="not json",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1


def test_post_ignores_non_python_files(tmp_path: Path) -> None:
    md = tmp_path / "notes.md"
    md.write_text("# x\n", encoding="utf-8")
    assert guard.run_post({"tool_input": {"file_path": str(md)}}) is None


def test_expand_braces() -> None:
    assert guard.expand_braces("T{0[1-9],2[01]}.txt") == ["T0[1-9].txt", "T2[01].txt"]
