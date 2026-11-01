"""T11: `metrics` and `domain` never import `anthropic` or `mcp`, statically or at runtime."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "plant_monitor"
PURE_PACKAGES = ("metrics", "domain")
FORBIDDEN = frozenset({"anthropic", "mcp"})


def imported_roots(source: str) -> set[str]:
    """Top-level names of every absolute import in `source`, including nested ones."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize(
    "source",
    [
        "import anthropic",
        "import anthropic.types as t",
        "from anthropic.types import Message",
        "from mcp import ClientSession",
        "import os, mcp.server",
        "def f() -> None:\n    import anthropic\n",
    ],
)
def test_import_scanner_detects_forbidden_imports(source: str) -> None:
    assert imported_roots(source) & FORBIDDEN


def test_import_scanner_ignores_lookalike_names() -> None:
    assert not imported_roots("import anthropic_tools\nfrom mcpx import y\nfrom . import mcp\n") & FORBIDDEN


@pytest.mark.parametrize("package", PURE_PACKAGES)
def test_pure_package_modules_never_import_model_sdks(package: str) -> None:
    files = sorted((PACKAGE / package).rglob("*.py"))
    assert files, f"no modules found under {package}"
    offenders = {
        str(path.relative_to(PACKAGE)): sorted(roots & FORBIDDEN)
        for path in files
        if (roots := imported_roots(path.read_text(encoding="utf-8"))) & FORBIDDEN
    }
    assert offenders == {}


def test_importing_engine_loads_no_model_sdk(tmp_path: Path) -> None:
    probe = (
        "import json, sys\n"
        "import plant_monitor.metrics.engine\n"
        f"print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in {sorted(FORBIDDEN)!r})))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False, cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
