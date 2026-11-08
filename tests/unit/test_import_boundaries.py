"""001 T11, 002 T15, 003 T2/T16, 004 T9, 005 T6: no model SDK in service code; layers import what they may."""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "plant_monitor"
PROJECT = "plant_monitor"
SDK_FREE_PACKAGES = ("metrics", "domain", "ingestion", "runner", "cases", "notify", "evaluation")
FORBIDDEN = frozenset({"anthropic", "mcp"})
ROOT = "<root>"
EVALUATION_ALLOWED = ("plant_monitor.domain", "plant_monitor.ingestion", "plant_monitor.evaluation")
SOURCES_EXTRA = ("plant_monitor.cases.registry.notices.read_deliverables",)
SQL_PATTERN = re.compile(
    "SELECT .+ FROM|INSERT INTO|UPDATE [a-z_]+ SET|DELETE FROM|PRAGMA |CREATE TABLE",
    re.DOTALL,
)
CASES_ALLOWED = ("plant_monitor.domain", "plant_monitor.metrics.thresholds", "plant_monitor.cases")


def imported_roots(source: str) -> set[str]:
    """Top-level names of every absolute import in 'source', including nested ones."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


def project_subpackages(source: str, package: str) -> set[str]:
    """'plant_monitor.<sub>' names imported by a module of dotted 'package', relative imports resolved."""
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


def project_modules(source: str, package: str) -> set[str]:
    """Dotted 'plant_monitor' names imported by a module of 'package'; 'from X import y' yields 'X.y'."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package.split(".")[: len(package.split(".")) - node.level + 1] if node.level else []
            module = ".".join([*base, *(node.module.split(".") if node.module else [])])
            names = [f"{module}.{alias.name}" for alias in node.names]
        found.update(name for name in names if name.split(".")[0] == PROJECT)
    return found


def disallowed_modules(source: str, package: str, allowed: tuple[str, ...]) -> set[str]:
    """Project names imported by the module that are neither an allowed module nor inside one."""
    return {
        name
        for name in project_modules(source, package)
        if not any(name == prefix or name.startswith(f"{prefix}.") for prefix in allowed)
    }


def package_of(path: Path) -> str:
    """Dotted package that contains the module at 'path'."""
    return ".".join((PROJECT, *path.relative_to(PACKAGE).parent.parts))


def modules_of(subpackage: str) -> list[Path]:
    """Every module file under a 'plant_monitor' subpackage."""
    files = sorted((PACKAGE / subpackage).rglob("*.py"))
    assert files, f"no modules found under {subpackage}"
    return files


def layer_offenders(files: list[Path], allowed: set[str]) -> dict[str, list[str]]:
    """Project subpackages each file imports beyond 'allowed'."""
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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from plant_monitor.metrics.thresholds import ResolutionThresholds", set()),
        ("from plant_monitor.metrics import thresholds", set()),
        ("from plant_monitor.domain.cases import Case\nimport plant_monitor.domain.enums", set()),
        ("from .lifecycle import step\nfrom . import registry", set()),
        ("from ..domain.models import Combination", set()),
        ("import sqlite3\nfrom collections.abc import Mapping", set()),
        (
            "from plant_monitor.metrics.engine import compute_metrics",
            {"plant_monitor.metrics.engine.compute_metrics"},
        ),
        ("from plant_monitor.metrics import engine", {"plant_monitor.metrics.engine"}),
        ("from plant_monitor.metrics import compute_metrics", {"plant_monitor.metrics.compute_metrics"}),
        ("from ..metrics.thresholdsx import y", {"plant_monitor.metrics.thresholdsx.y"}),
        ("import plant_monitor.runner.ports", {"plant_monitor.runner.ports"}),
        ("from plant_monitor import metrics", {"plant_monitor.metrics"}),
    ],
)
def test_module_scanner_reports_imports_outside_the_allowed_modules(source: str, expected: set[str]) -> None:
    """The cases rule is module-level, so the scanner must tell 'metrics.thresholds' from 'metrics.*'."""
    assert disallowed_modules(source, "plant_monitor.cases", CASES_ALLOWED) == expected


def sql_strings(source: str) -> list[str]:
    """String constants of 'source' that look like SQL statements."""
    return [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL_PATTERN.search(node.value)
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from plant_monitor.cases.registry.notices import read_deliverables", set()),
        (
            "from plant_monitor.cases.registry.notices import SqliteNoticeStore",
            {"plant_monitor.cases.registry.notices.SqliteNoticeStore"},
        ),
        (
            "from plant_monitor.cases.registry import SqliteRegistry",
            {"plant_monitor.cases.registry.SqliteRegistry"},
        ),
        ("from plant_monitor.cases.novelty import is_repeat", {"plant_monitor.cases.novelty.is_repeat"}),
        ("from plant_monitor import config", {"plant_monitor.config"}),
    ],
)
def test_sources_scanner_allows_exactly_read_deliverables_from_cases(source: str, expected: set[str]) -> None:
    allowed = (*EVALUATION_ALLOWED, *SOURCES_EXTRA)
    assert disallowed_modules(source, "plant_monitor.evaluation", allowed) == expected


@pytest.mark.parametrize(
    ("source", "found"),
    [
        ('q = "SELECT kind FROM notices"', True),
        ('q = "PRAGMA table_info(notices)"', True),
        ('"""Select the cases from the golden set."""', False),
        ("x = 1", False),
    ],
)
def test_sql_scanner_flags_statements_not_prose(source: str, found: bool) -> None:
    assert bool(sql_strings(source)) is found


# --- No model SDK ---


@pytest.mark.parametrize("package", SDK_FREE_PACKAGES)
def test_sdk_free_package_modules_never_import_model_sdks(package: str) -> None:
    offenders = {
        str(path.relative_to(PACKAGE)): sorted(roots & FORBIDDEN)
        for path in modules_of(package)
        if (roots := imported_roots(path.read_text(encoding="utf-8"))) & FORBIDDEN
    }
    assert offenders == {}


@pytest.mark.parametrize(
    "module",
    [
        "plant_monitor.metrics.engine",
        "plant_monitor.runner.series",
        "plant_monitor.cases.tracker",
        "plant_monitor.evaluation.scoring",
    ],
)
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


def test_cases_imports_only_domain_and_metrics_thresholds() -> None:
    offenders = {
        str(path.relative_to(PACKAGE)): sorted(extra)
        for path in modules_of("cases")
        if (extra := disallowed_modules(path.read_text(encoding="utf-8"), package_of(path), CASES_ALLOWED))
    }
    assert offenders == {}


def test_notify_imports_only_domain() -> None:
    assert layer_offenders(modules_of("notify"), {"domain", "notify"}) == {}


def test_cases_facts_and_templates_import_only_domain_and_the_pure_case_modules() -> None:
    allowed = ("plant_monitor.domain", "plant_monitor.cases.facts", "plant_monitor.cases.novelty")
    files = [PACKAGE / "cases" / "facts.py", PACKAGE / "cases" / "templates.py"]
    offenders = {
        str(path.relative_to(PACKAGE)): sorted(extra)
        for path in files
        if (extra := disallowed_modules(path.read_text(encoding="utf-8"), package_of(path), allowed))
    }
    assert offenders == {}


def test_runner_pipeline_and_outbox_import_only_service_layers() -> None:
    allowed = {"domain", "runner", "cases", "metrics", "notify"}
    files = [PACKAGE / "runner" / "pipeline.py", PACKAGE / "runner" / "outbox.py"]
    assert layer_offenders(files, allowed) == {}


def test_runner_pipeline_does_not_import_notify() -> None:
    allowed = {"domain", "runner", "cases", "metrics"}
    assert layer_offenders([PACKAGE / "runner" / "pipeline.py"], allowed) == {}


def test_runner_outbox_imports_only_domain_runner_and_notify() -> None:
    allowed = {"domain", "runner", "notify"}
    assert layer_offenders([PACKAGE / "runner" / "outbox.py"], allowed) == {}


# --- 005 evaluation (E38) ---


def test_evaluation_modules_import_only_domain_ingestion_and_evaluation() -> None:
    offenders = {
        str(path.relative_to(PACKAGE)): sorted(extra)
        for path in modules_of("evaluation")
        if (
            extra := disallowed_modules(
                path.read_text(encoding="utf-8"),
                package_of(path),
                (*EVALUATION_ALLOWED, *(SOURCES_EXTRA if path.name == "sources.py" else ())),
            )
        )
    }
    assert offenders == {}


def test_only_evaluation_sources_may_import_the_registry_reader() -> None:
    importers = sorted(
        path.name
        for path in modules_of("evaluation")
        if any(
            name.startswith("plant_monitor.cases")
            for name in project_modules(path.read_text(encoding="utf-8"), package_of(path))
        )
    )
    assert importers in ([], ["sources.py"])


def test_evaluation_never_imports_the_novelty_rules() -> None:
    """Noise is re-derived independently of the system it checks (ADR-0011)."""
    offenders = [
        path.name
        for path in modules_of("evaluation")
        if any(
            name.startswith("plant_monitor.cases.novelty")
            for name in project_modules(path.read_text(encoding="utf-8"), package_of(path))
        )
    ]
    assert offenders == []


def test_evaluation_has_no_sqlite_import_and_no_sql() -> None:
    imports = [
        path.name
        for path in modules_of("evaluation")
        if "sqlite3" in imported_roots(path.read_text(encoding="utf-8"))
    ]
    texts = [path.read_text(encoding="utf-8") for path in modules_of("evaluation")]
    statements = [s for text in texts for s in sql_strings(text)]
    assert (imports, statements) == ([], [])


def test_importing_evaluation_scoring_loads_no_cases_module_and_no_sqlite(tmp_path: Path) -> None:
    probe = (
        "import json, sys\n"
        "import plant_monitor.evaluation.scoring\n"
        "print(json.dumps(sorted(m for m in sys.modules "
        "if m == 'sqlite3' or m == 'plant_monitor.cases' or m.startswith('plant_monitor.cases.'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False, cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


# --- 006 logbooks and MCP (E18) ---

MCP_SERVER_ALLOWED = {"domain", "metrics", "cases", "logbooks", "mcp_server"}


def mcp_importers(sources: dict[str, str]) -> list[str]:
    """Relative paths of the sources outside 'mcp_server' that import 'mcp'."""
    return sorted(
        path
        for path, source in sources.items()
        if not path.startswith("mcp_server/") and "mcp" in imported_roots(source)
    )


def test_e18_only_mcp_server_imports_mcp() -> None:
    """E18: every package, including 'agents' once it exists, keeps 'mcp' out; only 'mcp_server' has it."""
    sources = {
        str(path.relative_to(PACKAGE).as_posix()): path.read_text(encoding="utf-8")
        for path in PACKAGE.rglob("*.py")
    }
    assert mcp_importers(sources) == []
    assert any(imported_roots(sources[p]) & {"mcp"} for p in sources if p.startswith("mcp_server/"))


@pytest.mark.parametrize("path", ["logbooks/store.py", "agents/runner.py"])
def test_e18_scanner_flags_import_mcp_under_logbooks_or_agents(path: str) -> None:
    """E18: a fixture source with 'import mcp' under 'logbooks' or 'agents' is flagged."""
    assert mcp_importers({path: "import mcp\n", "mcp_server/client.py": "import mcp\n"}) == [path]


def test_e18_logbooks_imports_only_domain_ingestion_and_logbooks_and_no_sdk() -> None:
    """E18: the 'logbooks' allow-list, and it joins the SDK-free scan."""
    assert layer_offenders(modules_of("logbooks"), {"domain", "ingestion", "logbooks"}) == {}
    sdk = [
        p.name for p in modules_of("logbooks") if imported_roots(p.read_text(encoding="utf-8")) & FORBIDDEN
    ]
    assert sdk == []


def test_e18_mcp_server_imports_only_its_allowed_layers_and_no_anthropic() -> None:
    """E18: 'mcp_server' never reads config, runner, agents or evaluation, nor 'anthropic'."""
    files = modules_of("mcp_server")
    assert layer_offenders(files, MCP_SERVER_ALLOWED) == {}
    assert [p.name for p in files if "anthropic" in imported_roots(p.read_text(encoding="utf-8"))] == []


def test_e18_verbatim_and_errors_import_nothing_from_the_project() -> None:
    """E18: the two shared 'domain' modules are leaves."""
    files = [PACKAGE / "domain" / "verbatim.py", PACKAGE / "domain" / "errors.py"]
    assert layer_offenders(files, set()) == {}
