"""008 T13: golden evidence availability on load (E23, R18)."""

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
import yaml
from eval_cause_builders import t21_shifts

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.evaluation.golden import load_golden
from plant_monitor.ingestion.errors import DataLoadError

from eval_builders import (
    Item,
    golden_alert,
    golden_cause,
    golden_evidence,
    golden_file,
    golden_news,
    write_golden,
)

SE = "S015-SUV-Europa"
FRAGMENT = "retuvo en calidad las SUV de exportación"
VERSIONED_GOLDEN = Path(__file__).resolve().parents[3] / "evals" / "golden"


def _policy() -> HeldOutPolicy:
    return HeldOutPolicy.from_calendar(t21_shifts(), "T21", True)


def _never_called(ids: frozenset[str]) -> Mapping[str, str]:
    raise AssertionError(f"logbook source called with {sorted(ids)}")


def _cause(notice: str, turno_id: str | None = None) -> Item:
    item = golden_cause(
        SE,
        notice,
        "retencion_de_calidad",
        "calidad",
        requires=["agent"],
        evidencia=golden_evidence("T08", FRAGMENT),
    )
    if turno_id is not None:
        item["turno_id"] = turno_id
    return item


def _alert_file() -> Item:
    return golden_file(["T08"], alerts=[golden_alert(SE, "S015")], causes=[_cause("alerta_inmediata")])


def _news_file() -> Item:
    news = golden_news("T08", SE, "abierto", "alta", "alta")
    return golden_file(["T08"], news=[news], causes=[_cause("informe_de_turno", "T08")])


def _versioned_source() -> Callable[[frozenset[str]], Mapping[str, str]]:
    """Per requested id, every versioned golden fragment citing it, joined by newlines."""
    fragments: dict[str, list[str]] = {}
    for path in sorted(VERSIONED_GOLDEN.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for cause in data.get("causes", []):
            evidence = cause.get("evidencia")
            if evidence:
                fragments.setdefault(evidence["bitacora"], []).append(evidence["fragmento"])
    return lambda ids: {turno: "\n".join(fragments.get(turno, [])) for turno in ids}


def test_e23a_evidence_that_closes_after_the_alert_snapshot_is_a_load_error(tmp_path: Path) -> None:
    write_golden(tmp_path, "day_x.yaml", _alert_file())
    with pytest.raises(DataLoadError) as info:
        load_golden(tmp_path, t21_shifts(), _policy(), _never_called)
    assert str(info.value) == (
        "day_x.yaml#causes[0]: logbook T08 is not available at S015: it closes at S016"
    )


@pytest.mark.parametrize("source", ["b_news_cause_citing_its_own_shift", "c_versioned_goldens"])
def test_e23bc_available_evidence_loads(tmp_path: Path, source: str) -> None:
    if source.startswith("b"):
        write_golden(tmp_path, "day_x.yaml", _news_file())
        golden = load_golden(tmp_path, t21_shifts(), _policy(), lambda ids: {"T08": FRAGMENT})
    else:
        golden = load_golden(VERSIONED_GOLDEN, t21_shifts(), _policy(), _versioned_source())
    assert golden.causes
