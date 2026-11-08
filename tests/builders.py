"""Shared synthetic builders for tests; snapshot payloads mirror the 'Sxxx.json' data contract."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

from plant_monitor.domain.cases import Case, CaseHistoryRow, CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics
from plant_monitor.ingestion.plant import load_shifts

if TYPE_CHECKING:
    from plant_monitor.domain.calendar import HeldOutPolicy

FIXTURE_PLANT = Path(__file__).resolve().parent / "fixtures" / "plant"
PICKUP_BRAZIL = Combination(modelo=Model.PICKUP, mercado=Market.BRAZIL)


def combination_of(case_id: str) -> Combination:
    """Combination encoded in a case id such as 'S015-Pickup-Brasil'."""
    _, model, market = case_id.split("-")
    return Combination(modelo=Model(model), mercado=Market(market))


def case_with(
    case_id: str,
    state: CaseState,
    minimum: Severity,
    peak: Severity | None,
    *,
    at: str | None = None,
    raised: bool = False,
    reported: tuple[CaseState, Severity, str] | None = None,
    clean_streak: int = 0,
) -> Case:
    """Case at snapshot 'at' (default: its opening); 'reported' is '(state, severity, snapshot)'."""
    opened_at = case_id.split("-")[0]
    last = at or opened_at
    return Case(
        case_id=case_id,
        combination=combination_of(case_id),
        opened_at=opened_at,
        state=state,
        minimum_severity=minimum,
        raised=raised,
        max_severity_since_report=peak,
        clean_streak=clean_streak,
        last_snapshot_id=last,
        last_reported_at=None if reported is None else reported[2],
        last_reported_state=None if reported is None else reported[0],
        last_reported_severity=None if reported is None else reported[1],
        resolved_at=last if state is CaseState.RESOLVED else None,
    )


def measured(
    combination: Combination,
    gap_units: float,
    gap_pct: float | None,
    delay_days: float | None,
    bottleneck: Stage | None,
    gap_severity: Severity,
    delay_severity: Severity,
) -> CombinationMetrics:
    """Metrics from a spec facts tuple; the minimum is the max of gap and delay severity (§2)."""
    return CombinationMetrics(
        combination=combination,
        progress=0,
        cumulative_plan=0.0,
        gap_units=gap_units,
        gap_pct=gap_pct,
        delay_days=delay_days,
        delay_beyond_horizon=delay_days is None,
        bottleneck=bottleneck,
        gap_severity=gap_severity,
        delay_severity=delay_severity,
        minimum_severity=max(gap_severity, delay_severity),
    )


def history_row(
    case_id: str,
    snapshot_id: str,
    bottleneck: Stage | None,
    *,
    minimum: Severity = Severity.MEDIUM,
    raised: bool = False,
    state: CaseState = CaseState.FOLLOW_UP,
) -> CaseHistoryRow:
    """History row of 'case_id' at 'snapshot_id'; the default minimum is a deviation (Q-32 cause row)."""
    return CaseHistoryRow(
        case_id=case_id,
        snapshot_id=snapshot_id,
        state=state,
        minimum_severity=minimum,
        raised=raised,
        gap_units=0.0,
        gap_pct=None,
        delay_days=0.0,
        bottleneck=bottleneck,
        clean_streak=0,
    )


def metrics_with(
    minimum: Severity,
    *,
    combination: Combination = PICKUP_BRAZIL,
    gap_units: float = 0.0,
    gap_pct: float | None = None,
    delay_days: float | None = None,
    bottleneck: Stage | None = None,
) -> CombinationMetrics:
    """Synthetic metrics for one combination; only 'minimum' drives the case lifecycle."""
    return CombinationMetrics(
        combination=combination,
        progress=0,
        cumulative_plan=0.0,
        gap_units=gap_units,
        gap_pct=gap_pct,
        delay_days=delay_days,
        delay_beyond_horizon=False,
        bottleneck=bottleneck,
        gap_severity=minimum,
        delay_severity=Severity.NONE,
        minimum_severity=minimum,
    )


def unit_payload(**overrides: object) -> dict[str, object]:
    """Snapshot unit as it appears in Sxxx.json."""
    payload: dict[str, object] = {
        "unidad_id": "U00001",
        "modelo": "Sedán",
        "mercado": "Local",
        "color": "Gris Plata",
        "etapa": "montaje",
        "ingreso_etapa": "2026-03-02T08:00",
        "retrabajos": 0,
        "embarque_asignado": "LOC-0302",
    }
    payload.update(overrides)
    return payload


def released_payload(**overrides: object) -> dict[str, object]:
    """Released unit as it appears in Sxxx.json liberadas."""
    payload: dict[str, object] = {
        "unidad_id": "U00900",
        "modelo": "SUV",
        "mercado": "Brasil",
        "hora": "2026-03-02T06:21",
    }
    payload.update(overrides)
    return payload


def snapshot_payload(
    units: list[dict[str, object]] | None = None,
    released: list[dict[str, object]] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Snapshot payload with S001 defaults: two units and one release."""
    payload: dict[str, object] = {
        "snapshot_id": "S001",
        "timestamp": "2026-03-02T10:00",
        "turno": "T01",
        "unidades": units
        if units is not None
        else [
            unit_payload(),
            unit_payload(
                unidad_id="U00002",
                modelo="SUV",
                mercado="Brasil",
                etapa="pintura",
                ingreso_etapa="2026-03-02T09:00",
                retrabajos=1,
                embarque_asignado="BRA-0303",
            ),
        ],
        "liberadas": released if released is not None else [released_payload()],
    }
    payload.update(overrides)
    return payload


def write_snapshot(tmp_path: Path, payload: dict[str, object], name: str = "S001.json") -> Path:
    """Write a snapshot JSON as UTF-8 with non-ASCII kept literal."""
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def held_out_policy(first_shift: str = "T03", *, is_open: bool = False) -> HeldOutPolicy:
    """Policy over the fixture calendar (T01 to T03); imported lazily so older tests still collect."""
    from plant_monitor.domain.calendar import HeldOutPolicy

    return HeldOutPolicy.from_calendar(load_shifts(FIXTURE_PLANT / "turnos.csv"), first_shift, is_open)
