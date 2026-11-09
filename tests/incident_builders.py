"""Builders for the 008 incident fixture (IF): snapshot payloads from gaps and delayed units."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import Shift
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds

from builders import FIXTURE_PLANT, released_payload, snapshot_payload, unit_payload, write_snapshot

INCIDENTS = Path(__file__).resolve().parent / "fixtures" / "incidents"
FIRST_START = datetime(2026, 3, 2, 6, 0)
SNAPSHOT_STEP = timedelta(hours=4)
PLAN_PER_SNAPSHOT = 5
"""Every combination plans 10 units per 8 h shift, so the cumulative plan grows 5 per snapshot."""

type Combo = tuple[Model, Market]
type Gaps = dict[Combo, dict[int, int]]
type Units = dict[int, list[dict[str, object]]]

SEL: Combo = (Model.SEDAN, Market.LOCAL)
SL: Combo = (Model.SUV, Market.LOCAL)
SE: Combo = (Model.SUV, Market.EUROPE)
PL: Combo = (Model.PICKUP, Market.LOCAL)
PB: Combo = (Model.PICKUP, Market.BRAZIL)
PE: Combo = (Model.PICKUP, Market.EUROPE)


def delayed_unit(combo: Combo, stage: Stage, since: str, shipment: str, unit_id: str) -> dict[str, object]:
    """One in-plant unit of 'combo' in 'stage' since 'since', assigned to 'shipment'."""
    return unit_payload(
        unidad_id=unit_id,
        modelo=str(combo[0]),
        mercado=str(combo[1]),
        etapa=str(stage),
        ingreso_etapa=since,
        retrabajos=0,
        embarque_asignado=shipment,
    )


@dataclass
class IncidentScenario:
    """Gap in units per combination and snapshot number, and the delayed units per snapshot number."""

    gaps: Gaps = field(default_factory=dict)
    units: Units = field(default_factory=dict)


def incident_scenario() -> IncidentScenario:
    """The IF as the spec's notation gives it; tests edit the returned copy for their variants."""
    se_unit = delayed_unit(SE, Stage.QUALITY, "2026-03-02T20:00", "EUR-0305", "U-SE-001")
    pl_unit = delayed_unit(PL, Stage.ASSEMBLY, "2026-03-03T08:00", "LOC-0304", "U-PL-001")
    pb_unit = delayed_unit(PB, Stage.ASSEMBLY, "2026-03-03T08:00", "BRA-0304", "U-PB-001")
    pe_unit = delayed_unit(PE, Stage.ASSEMBLY, "2026-03-03T14:00", "EUR-0305", "U-PE-001")
    return IncidentScenario(
        gaps={
            SEL: {1: -2},
            SE: {4: -1, 5: -4, 6: -4},
            PL: {9: -2, 10: -4, 11: -7, 12: -11},
            PB: {9: -2, 10: -4, 11: -7, 12: -11},
            PE: {10: -2, 11: -6, 12: -11},
        },
        units={5: [se_unit], 6: [se_unit], 10: [pl_unit, pb_unit], 11: [pl_unit, pb_unit, pe_unit]},
    )


def incident_shifts() -> list[Shift]:
    """IF 'turnos.csv': T01 to T06 over S001 to S012."""
    return load_shifts(INCIDENTS / "planta" / "turnos.csv")


def incident_context() -> PlantContext:
    """IF plant context: its shifts and plan; standards, shipments and thresholds from the plant fixture."""
    shifts = incident_shifts()
    return PlantContext(
        plan=load_plan(INCIDENTS / "planta" / "plan_produccion.csv", shifts),
        shifts=shifts,
        standards=StandardsTable.from_rows(load_standards(FIXTURE_PLANT / "tiempos_estandar.csv")),
        shipments=ShipmentsTable.from_rows(load_shipments(FIXTURE_PLANT / "embarques.csv")),
        thresholds=load_thresholds(FIXTURE_PLANT / "umbrales.yaml"),
    )


def incident_timestamp(number: int) -> datetime:
    """Time of snapshot S<number>: the shift start plus 4 h per snapshot."""
    return FIRST_START + SNAPSHOT_STEP * number


def _progress(scenario: IncidentScenario, combo: Combo, number: int) -> int:
    """Cumulative releases that put 'combo' at its scenario gap in snapshot 'number'."""
    if number == 0:
        return 0
    return PLAN_PER_SNAPSHOT * number + scenario.gaps.get(combo, {}).get(number, 0)


def incident_snapshot(snapshot_id: str, scenario: IncidentScenario | None = None) -> dict[str, object]:
    """Payload of one IF snapshot: the releases that reach each scenario gap, and its delayed units."""
    scenario = scenario or incident_scenario()
    number = int(snapshot_id.removeprefix("S"))
    timestamp = incident_timestamp(number)
    hour = (timestamp - timedelta(hours=1)).isoformat(timespec="minutes")
    released: list[dict[str, object]] = []
    for model in Model:
        for market in Market:
            combo = (model, market)
            new = _progress(scenario, combo, number) - _progress(scenario, combo, number - 1)
            if new < 0:
                raise ValueError(f"{snapshot_id}: the gap of {model} x {market} needs {new} releases")
            released += [
                released_payload(
                    unidad_id=f"{snapshot_id}-{model[:2]}-{market[:2]}-{n:02d}",
                    modelo=str(model),
                    mercado=str(market),
                    hora=hour,
                )
                for n in range(1, new + 1)
            ]
    return snapshot_payload(
        list(scenario.units.get(number, [])),
        released,
        snapshot_id=snapshot_id,
        timestamp=timestamp.isoformat(timespec="minutes"),
        turno=f"T{(number + 1) // 2:02d}",
    )


def write_incident_series(
    directory: Path, snapshot_ids: Sequence[str], scenario: IncidentScenario | None = None
) -> list[Arrival]:
    """Write the named IF snapshots under 'directory' and return their arrivals in the given order."""
    directory.mkdir(parents=True, exist_ok=True)
    arrivals: list[Arrival] = []
    for orden, snapshot_id in enumerate(snapshot_ids, start=1):
        payload = incident_snapshot(snapshot_id, scenario)
        path = write_snapshot(directory, payload, f"{snapshot_id}.json")
        received = datetime.fromisoformat(str(payload["timestamp"]))
        arrivals.append(Arrival(orden=orden, snapshot_id=snapshot_id, archivo=path, recibido=received))
    return arrivals
