"""Data, settings and seams shared by the 012 command-line integration tests."""

import shutil
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import pytest
from incident_builders import INCIDENTS, copy_incident_logbooks, write_incident_series
from multi_agent_builders import ALL, STARTED

from plant_monitor.agents.model import ModelPort
from plant_monitor.config import Settings
from plant_monitor.runner.cli import CliDeps

from builders import CRIT, FIXTURE_PLANT

ARR13: tuple[str, ...] = (*ALL[:4], ALL[3], *ALL[4:])


def write_cli_data(root: Path, ids: Sequence[str]) -> Path:
    """Write the data directory for the arrivals 'ids' (a repeated id reuses its file) and return it."""
    plant = root / "planta"
    plant.mkdir(parents=True, exist_ok=True)
    for name in ("turnos.csv", "plan_produccion.csv"):
        shutil.copy(INCIDENTS / "planta" / name, plant / name)
    for name in ("tiempos_estandar.csv", "embarques.csv"):
        shutil.copy(FIXTURE_PLANT / name, plant / name)
    rules = root / "reglas"
    rules.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_PLANT / "umbrales.yaml", rules / "umbrales.yaml")
    (rules / "criterio.md").write_text(CRIT, encoding="utf-8-sig")
    copy_incident_logbooks(root / "bitacoras")
    arrivals = write_incident_series(root / "snapshots", ids)
    lines = ["orden,snapshot_id,archivo,recibido"] + [
        f"{a.orden},{a.snapshot_id},{a.archivo.name},{a.recibido.isoformat(timespec='minutes')}"
        for a in arrivals
    ]
    (root / "snapshots" / "llegadas.csv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return root


def cli_settings(data: Path, out: Path, **overrides: object) -> Settings:
    """The spec's SET (key 'k', held-out guard open from T06) with 'overrides'; callers isolate the env."""
    values: dict[str, object] = {
        "anthropic_api_key": "k",
        "data_dir": data,
        "output_dir": out,
        "heldout_open": True,
        "heldout_first_shift": "T06",
    }
    return Settings.model_validate({**values, **overrides})


def no_sleep(seconds: float) -> None:
    """Fail the test: a run without '--speed' must never sleep (I16)."""
    pytest.fail(f"slept {seconds} s")


def never_model(settings: Settings) -> ModelPort:
    """Fail the test: this run must not build a model."""
    pytest.fail("the model factory was called")


def cli_deps(
    settings: Settings,
    model: ModelPort | None = None,
    *,
    sleep: Callable[[float], None] = no_sleep,
    now: datetime = STARTED,
    ticks: Sequence[float] = (0.0, 1.0),
) -> CliDeps:
    """Seams with a fixed clock; a None 'model' fails the test if the factory is called."""
    clock = iter(ticks)
    return CliDeps(
        settings=lambda: settings,
        model_factory=never_model if model is None else (lambda _settings: model),
        sleep=sleep,
        monotonic=lambda: next(clock),
        now=lambda: now,
    )


# --- 012 T5 ---


class Sleeps:
    """A 'sleep' that records its calls and raises 'KeyboardInterrupt' on call number 'interrupt_at'."""

    def __init__(self, interrupt_at: int | None = None) -> None:
        self.calls: list[float] = []
        self._interrupt_at = interrupt_at

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if self._interrupt_at == len(self.calls):
            raise KeyboardInterrupt
