"""T10: compute_metrics integrates progress, plan, gap, delay, bottleneck and severity for one snapshot."""

import dataclasses
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import (
    Combination,
    CombinationMetrics,
    PlanRow,
    ReleasedUnit,
    Snapshot,
    Unit,
    all_combinations,
)
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext, compute_metrics
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
SUV_BRAZIL = Combination(modelo=Model.SUV, mercado=Market.BRAZIL)
SUV_LOCAL = Combination(modelo=Model.SUV, mercado=Market.LOCAL)
PICKUP_EUROPE = Combination(modelo=Model.PICKUP, mercado=Market.EUROPE)


def dt(text: str) -> datetime:
    """Naive plant-local datetime from ISO text."""
    return datetime.fromisoformat(text)


def unit(
    unit_id: str,
    model: Model,
    market: Market,
    stage: Stage,
    since: str,
    shipment: str,
    *,
    rework: int = 0,
) -> Unit:
    """Snapshot unit varying only the fields the metrics read."""
    return Unit(
        unidad_id=unit_id,
        modelo=model,
        mercado=market,
        color="Gris Plata",
        etapa=stage,
        ingreso_etapa=dt(since),
        retrabajos=rework,
        embarque_asignado=shipment,
    )


def released(
    unit_id: str, hour: str, model: Model = Model.SEDAN, market: Market = Market.LOCAL
) -> ReleasedUnit:
    """Released unit as listed in a snapshot's liberadas."""
    return ReleasedUnit(unidad_id=unit_id, modelo=model, mercado=market, hora=dt(hour))


def snapshot(
    snapshot_id: str,
    timestamp: str,
    shift: str,
    units: tuple[Unit, ...] = (),
    releases: tuple[ReleasedUnit, ...] = (),
) -> Snapshot:
    """Snapshot built in Python instead of a JSON file."""
    return Snapshot(
        snapshot_id=snapshot_id, timestamp=dt(timestamp), turno=shift, unidades=units, liberadas=releases
    )


def with_plan(plan: list[PlanRow], shift_id: str, combo: Combination, units: int) -> list[PlanRow]:
    """Copy of the plan with one shift and combination row changed."""
    return [
        row.model_copy(update={"unidades_plan": units})
        if (row.turno_id, row.modelo, row.mercado) == (shift_id, combo.modelo, combo.mercado)
        else row
        for row in plan
    ]


@pytest.fixture
def ctx() -> PlantContext:
    """Plant context from the fixture CSVs and umbrales.yaml (T01-T03, every plan row as in the CSV)."""
    shifts = load_shifts(FIXTURES / "turnos.csv")
    return PlantContext(
        plan=load_plan(FIXTURES / "plan_produccion.csv", shifts),
        shifts=shifts,
        standards=StandardsTable.from_rows(load_standards(FIXTURES / "tiempos_estandar.csv")),
        shipments=ShipmentsTable.from_rows(load_shipments(FIXTURES / "embarques.csv")),
        thresholds=load_thresholds(FIXTURES / "umbrales.yaml"),
    )


# S001 = T01 mid (06:00-14:00, mid at 10:00). Hand-computed with the fixture files:
# Sedán/Local (E1 + E4): plan 12 -> cum 6.0; 2 released -> gap -4.0, -4/36 = -11.1 % -> gap media.
#   SL-M montaje since 08:00, LOC-0302: 480 + calidad 180 -> 21:00 > cut 14:00 -> LOC-0303, delay 1 -> media.
#   SL-Y in patio is excluded. No unit over standard + 60 -> bottleneck None. Minimum media.
# SUV/Brasil (E6 + E5): plan 6 -> cum 3.0; 0 released -> gap -3.0, -3/18 = -16.7 %, 3 >= minimo 3 -> media.
#   SB-P pintura since 09:00, no rework, BRA-0303: 420 + 660 + 180 -> 03-03 07:00 > cut 06:00 -> BRA-0304, 1.
#   SB-R pintura since 09:00, rework 1, BRA-0303: 300 + 660 + 180 -> 03-03 05:00 -> BRA-0303, delay 0.
#   Max delay 1 -> alta (Brasil). SB-R is repainting -> bottleneck pintura. Minimum max(media, alta) = alta.
# SUV/Local (untouched): plan 8 -> cum 4.0, gap -4.0, -4/24 = -16.7 % -> gap media; delay 0 -> minimum media.
# Pickup/Europa (untouched): plan 4 -> cum 2.0, gap -2.0, 2 < minimo 3 -> no gap severity; delay 0 -> none.
S001_AT = "2026-03-02T10:00"
S001_UNITS = (
    unit("SL-M", Model.SEDAN, Market.LOCAL, Stage.ASSEMBLY, "2026-03-02T08:00", "LOC-0302"),
    unit("SL-Y", Model.SEDAN, Market.LOCAL, Stage.YARD, "2026-03-01T08:00", "LOC-0302"),
    unit("SB-P", Model.SUV, Market.BRAZIL, Stage.PAINT, "2026-03-02T09:00", "BRA-0303"),
    unit("SB-R", Model.SUV, Market.BRAZIL, Stage.PAINT, "2026-03-02T09:00", "BRA-0303", rework=1),
)
S001_RELEASES = (released("R1", "2026-03-02T07:10"), released("R2", "2026-03-02T08:40"))


@pytest.fixture
def s001() -> Snapshot:
    """T01 mid snapshot with the two interesting combinations."""
    return snapshot("S001", S001_AT, "T01", S001_UNITS, S001_RELEASES)


@pytest.fixture
def s001_metrics(s001: Snapshot, ctx: PlantContext) -> dict[Combination, CombinationMetrics]:
    """Engine output for S001 as the first snapshot of the series."""
    return compute_metrics(s001, [], ctx)


def test_fixture_s001_is_t01_mid_at_ten(ctx: PlantContext) -> None:
    t01 = next(shift for shift in ctx.shifts if shift.turno_id == "T01")
    assert t01.snapshot_medio == "S001"
    assert t01.inicio + (t01.fin - t01.inicio) / 2 == dt(S001_AT)


def test_plant_context_is_frozen(ctx: PlantContext) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(ctx, "plan", [])  # noqa: B010


def test_result_has_all_nine_combinations_keyed_by_their_own(
    s001_metrics: dict[Combination, CombinationMetrics],
) -> None:
    assert set(s001_metrics) == set(all_combinations())
    assert all(m.combination == combo for combo, m in s001_metrics.items())


def test_e1_e4_sedan_local_gap_and_missed_truck_are_media(
    s001_metrics: dict[Combination, CombinationMetrics],
) -> None:
    m = s001_metrics[SEDAN_LOCAL]
    assert m.progress == 2
    assert m.cumulative_plan == 6.0
    assert m.gap_units == -4.0
    assert m.gap_pct == pytest.approx(-4 / 36 * 100)
    assert m.gap_severity is Severity.MEDIUM
    assert m.delay_days == 1.0
    assert m.delay_beyond_horizon is False
    assert m.delay_severity is Severity.MEDIUM
    assert m.bottleneck is None
    assert m.minimum_severity is Severity.MEDIUM
    assert m.has_deviation


def test_e6_suv_brazil_delay_alta_beats_gap_media(
    s001_metrics: dict[Combination, CombinationMetrics],
) -> None:
    m = s001_metrics[SUV_BRAZIL]
    assert m.progress == 0
    assert m.cumulative_plan == 3.0
    assert m.gap_units == -3.0
    assert m.gap_pct == pytest.approx(-3 / 18 * 100)
    assert m.gap_severity is Severity.MEDIUM
    assert m.delay_days == 1.0
    assert m.delay_beyond_horizon is False
    assert m.delay_severity is Severity.HIGH
    assert m.bottleneck is Stage.PAINT
    assert m.minimum_severity is Severity.HIGH
    assert m.has_deviation


def test_untouched_combination_below_minimum_units_has_no_deviation(
    s001_metrics: dict[Combination, CombinationMetrics],
) -> None:
    m = s001_metrics[PICKUP_EUROPE]
    assert m.progress == 0
    assert m.cumulative_plan == 2.0
    assert m.gap_units == -2.0
    assert m.gap_pct == pytest.approx(-2 / 12 * 100)
    assert m.gap_severity is Severity.NONE
    assert m.delay_days == 0.0
    assert m.delay_beyond_horizon is False
    assert m.delay_severity is Severity.NONE
    assert m.bottleneck is None
    assert m.minimum_severity is Severity.NONE
    assert not m.has_deviation


def test_untouched_combination_behind_plan_deviates_from_gap_alone(
    s001_metrics: dict[Combination, CombinationMetrics],
) -> None:
    m = s001_metrics[SUV_LOCAL]
    assert m.gap_units == -4.0
    assert m.gap_pct == pytest.approx(-4 / 24 * 100)
    assert m.gap_severity is Severity.MEDIUM
    assert m.delay_days == 0.0
    assert m.delay_severity is Severity.NONE
    assert m.minimum_severity is Severity.MEDIUM


def test_released_so_far_including_current_snapshot_is_idempotent(s001: Snapshot, ctx: PlantContext) -> None:
    assert compute_metrics(s001, s001.liberadas, ctx) == compute_metrics(s001, [], ctx)


def test_released_so_far_accepts_a_one_shot_iterator(s001: Snapshot, ctx: PlantContext) -> None:
    once: Iterator[ReleasedUnit] = iter(s001.liberadas)
    assert compute_metrics(s001, once, ctx) == compute_metrics(s001, [], ctx)


# S002 = T01 closing at 14:00: R1, R2 earlier plus R2 (re-listed) and R3 now -> 3 distinct (E3).
# Sedán/Local cum 12.0, gap -9.0, -9/36 = -25 % -> gap alta; no units -> delay 0 -> minimum alta.
S002_RELEASES = (released("R2", "2026-03-02T08:40"), released("R3", "2026-03-02T12:00"))


def test_e3_closing_snapshot_adds_current_releases_counting_distinct_ids(ctx: PlantContext) -> None:
    s002 = snapshot("S002", "2026-03-02T14:00", "T01", releases=S002_RELEASES)
    m = compute_metrics(s002, S001_RELEASES, ctx)[SEDAN_LOCAL]
    assert m.progress == 3
    assert m.cumulative_plan == 12.0
    assert m.gap_units == -9.0
    assert m.gap_pct == pytest.approx(-25.0)
    assert m.gap_severity is Severity.HIGH
    assert m.delay_days == 0.0
    assert m.minimum_severity is Severity.HIGH


def test_releases_of_earlier_snapshots_with_duplicates_are_idempotent(ctx: PlantContext) -> None:
    s002 = snapshot("S002", "2026-03-02T14:00", "T01", releases=S002_RELEASES)
    once = compute_metrics(s002, S001_RELEASES, ctx)
    assert compute_metrics(s002, [*S001_RELEASES, *S002_RELEASES], ctx) == once


# S003 = T02 mid at 18:00 with T02 Sedán/Local set to 6: cum 12 + 3 = 15, gap -15.
# Daily plan is the current shift's 6 x 3 = 18 -> -83.3 % (using T01's 12 would give -41.7 %).
def test_daily_plan_is_current_shift_plan_times_three(ctx: PlantContext) -> None:
    six = dataclasses.replace(ctx, plan=with_plan(ctx.plan, "T02", SEDAN_LOCAL, 6))
    m = compute_metrics(snapshot("S003", "2026-03-02T18:00", "T02"), [], six)[SEDAN_LOCAL]
    assert m.cumulative_plan == 15.0
    assert m.gap_units == -15.0
    assert m.gap_pct == pytest.approx(-15 / 18 * 100)
    assert m.gap_severity is Severity.CRITICAL


# S003 with T02 Sedán/Local set to 0 and 6 released: cum 12 + 0 = 12, gap -6, daily plan 0 -> gap_pct None.
def test_e15_zero_current_shift_plan_gives_no_gap_pct_or_gap_severity(ctx: PlantContext) -> None:
    zero = dataclasses.replace(ctx, plan=with_plan(ctx.plan, "T02", SEDAN_LOCAL, 0))
    six_released = [released(f"R{i}", "2026-03-02T09:00") for i in range(6)]
    m = compute_metrics(snapshot("S003", "2026-03-02T18:00", "T02"), six_released, zero)[SEDAN_LOCAL]
    assert m.progress == 6
    assert m.cumulative_plan == 12.0
    assert m.gap_units == -6.0
    assert m.gap_pct is None
    assert m.gap_severity is Severity.NONE
    assert m.delay_severity is Severity.NONE
    assert m.minimum_severity is Severity.NONE


# S006 = T03 closing at 03-03 06:00. SUV/Brasil in carroceria since 06:00, BRA-0304:
# 360 + 480 + 660 + 180 = 1680 min -> 03-04 10:00, after the last Brasil cut-off 03-04 06:00 -> None.
def test_e14_beyond_horizon_combination_is_critica(ctx: PlantContext) -> None:
    body = unit("SB-B", Model.SUV, Market.BRAZIL, Stage.BODY, "2026-03-03T06:00", "BRA-0304")
    m = compute_metrics(snapshot("S006", "2026-03-03T06:00", "T03", (body,)), [], ctx)[SUV_BRAZIL]
    assert m.delay_days is None
    assert m.delay_beyond_horizon is True
    assert m.delay_severity is Severity.CRITICAL
    assert m.minimum_severity is Severity.CRITICAL


# Spec 002 E17 (Q-20): S001 releases U1, U2 as Sedán/Local; S002 (T01 closing) releases U2, U3 as SUV/Local.
# U2 stays in Sedán/Local (first release): Sedán/Local 2, cum 12 -> gap -10; SUV/Local 1, cum 8 -> gap -7.
E17_S001_RELEASES = (released("U1", "2026-03-02T07:10"), released("U2", "2026-03-02T08:40"))
E17_S002_RELEASES = (
    released("U2", "2026-03-02T12:00", Model.SUV, Market.LOCAL),
    released("U3", "2026-03-02T13:00", Model.SUV, Market.LOCAL),
)


def test_spec002_e17_unit_released_again_in_new_combination_counts_in_its_first(ctx: PlantContext) -> None:
    s002 = snapshot("S002", "2026-03-02T14:00", "T01", releases=E17_S002_RELEASES)
    result = compute_metrics(s002, E17_S001_RELEASES, ctx)
    suv_local = result[SUV_LOCAL]
    assert suv_local.progress == 1
    assert suv_local.cumulative_plan == 8.0
    assert suv_local.gap_units == -7.0
    sedan_local = result[SEDAN_LOCAL]
    assert sedan_local.progress == 2
    assert sedan_local.gap_units == -10.0


# Spec 002 E21 (Q-20): U9 is in S001 unidades as Sedán/Local but only ever released, in S002, as SUV/Local.
E21_S001 = snapshot(
    "S001",
    S001_AT,
    "T01",
    (unit("U9", Model.SEDAN, Market.LOCAL, Stage.QUALITY, "2026-03-02T09:00", "LOC-0302"),),
)
E21_S002_RELEASES = (released("U9", "2026-03-02T12:00", Model.SUV, Market.LOCAL),)


def test_spec002_e21_characterization_progress_follows_first_release_not_first_sighting(
    ctx: PlantContext,
) -> None:
    """Characterization: passes before Q-20; U9 counts under SUV/Local only."""
    s002 = snapshot("S002", "2026-03-02T14:00", "T01", releases=E21_S002_RELEASES)
    result = compute_metrics(s002, E21_S001.liberadas, ctx)
    assert result[SUV_LOCAL].progress == 1
    assert result[SEDAN_LOCAL].progress == 0


# Spec 002 E16 (Q-19): S005 = T03 mid at 03-03 02:00; calidad entry at 03:00 clamps to 0 elapsed.
# 180 min -> 05:00 < BRA-0303 cut-off 06:00 -> delay 0 (unclamped would be 06:00 -> BRA-0304, alta).
def test_spec002_e16_characterization_future_stage_entry_has_no_delay_severity(ctx: PlantContext) -> None:
    """Characterization: passes with today's code; the Q-19 clamp keeps SUV/Brasil on time."""
    future = unit("U00051", Model.SUV, Market.BRAZIL, Stage.QUALITY, "2026-03-03T03:00", "BRA-0303")
    m = compute_metrics(snapshot("S005", "2026-03-03T02:00", "T03", (future,)), [], ctx)[SUV_BRAZIL]
    assert m.delay_days == 0.0
    assert m.delay_beyond_horizon is False
    assert m.delay_severity is Severity.NONE


def test_e17_snapshot_absent_from_turnos_raises_naming_it(ctx: PlantContext) -> None:
    with pytest.raises(ValueError, match="S999"):
        compute_metrics(snapshot("S999", S001_AT, "T01", S001_UNITS, S001_RELEASES), [], ctx)
