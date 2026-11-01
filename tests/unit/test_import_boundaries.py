"""001 T11, 002 T15: no model SDK in pure, ingestion or runner code; layers import only what they may."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "plant_monitor"
PROJECT = "plant_monitor"
SDK_FREE_PACKAGES = ("metrics", "domain", "ingestion", "runner")
FORBIDDEN = frozenset({"anthropic", "mcp"})
ROOT = "<root>"


def imported_roots(source: str) -> set[str]:
    """Top-level names of every absolute import in `source`, including nested ones."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


def project_subpackages(source: str, package: str) -> set[str]:
    """`plant_monitor.<sub>` names imported by a module of dotted `package`, relative imports resolved."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        targets: list[list[str]] = []
        if isinstance(node, ast.Import):
            targets = [alias.name.split(".") for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package.split(".")[: len(package.split(".")) - node.level + 1] if node.level else []
            module = [*base, *(node.module.split(".") if node.module else [])]
            targets = [[*module, alias.name] for alias in node.names] if len(module) == 1 else [module]
        for parts in targets:
            if parts[0] == PROJECT:
                found.add(parts[1] if len(parts) > 1 else ROOT)
    return found


def package_of(path: Path) -> str:
    """Dotted package that contains the module at `path`."""
    return ".".join((PROJECT, *path.relative_to(PACKAGE).parent.parts))


def modules_of(subpackage: str) -> list[Path]:
    """Every module file under a `plant_monitor` subpackage."""
    files = sorted((PACKAGE / subpackage).rglob("*.py"))
    assert files, f"no modules found under {subpackage}"
    return files


def layer_offenders(files: list[Path], allowed: set[str]) -> dict[str, list[str]]:
    """Project subpackages each file imports beyond `allowed`."""
    offenders: dict[str, list[str]] = {}
    for path in files:
        extra = project_subpackages(path.read_text(encoding="utf-8"), package_of(path)) - allowed
        if extra:
            offenders[str(path.relative_to(PACKAGE))] = sorted(extra)
    return offenders


# --- Scanners ---


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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from plant_monitor.domain.models import Shift", {"domain"}),
        ("import plant_monitor.metrics.engine as engine", {"metrics"}),
        ("from plant_monitor import config", {"config"}),
        ("import plant_monitor", {ROOT}),
        ("import json\nfrom plant_monitor.ingestion.errors import DataLoadError", {"ingestion"}),
        ("def f() -> None:\n    from plant_monitor.metrics import engine\n", {"metrics"}),
        ("from .errors import DataLoadError", {"ingestion"}),
        ("from . import rows", {"ingestion"}),
        ("from ..domain.models import Shift", {"domain"}),
        ("from .. import runner", {"runner"}),
        ("import plant_monitor_extra\nfrom plant_monitorx import y", set()),
    ],
)
def test_project_scanner_reports_subpackages(source: str, expected: set[str]) -> None:
    assert project_subpackages(source, "plant_monitor.ingestion") == expected


# --- No model SDK ---


@pytest.mark.parametrize("package", SDK_FREE_PACKAGES)
def test_sdk_free_package_modules_never_import_model_sdks(package: str) -> None:
    offenders = {
        str(path.relative_to(PACKAGE)): sorted(roots & FORBIDDEN)
        for path in modules_of(package)
        if (roots := imported_roots(path.read_text(encoding="utf-8"))) & FORBIDDEN
    }
    assert offenders == {}


@pytest.mark.parametrize("module", ["plant_monitor.metrics.engine", "plant_monitor.runner.series"])
def test_importing_module_loads_no_model_sdk(tmp_path: Path, module: str) -> None:
    probe = (
        "import json, sys\n"
        f"import {module}\n"
        f"print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in {sorted(FORBIDDEN)!r})))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False, cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


# --- Layers ---


def test_domain_imports_nothing_from_the_project() -> None:
    assert layer_offenders(modules_of("domain"), {"domain"}) == {}


def test_ingestion_imports_only_domain() -> None:
    assert layer_offenders(modules_of("ingestion"), {"domain", "ingestion"}) == {}


def test_runner_checks_imports_only_domain() -> None:
    assert layer_offenders([PACKAGE / "runner" / "checks.py"], {"domain"}) == {}


def test_runner_series_imports_only_domain_ingestion_and_runner() -> None:
    allowed = {"domain", "ingestion", "runner"}
    assert layer_offenders([PACKAGE / "runner" / "series.py"], allowed) == {}
