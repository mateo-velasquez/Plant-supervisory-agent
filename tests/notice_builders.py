"""Synthetic notice and report builders for 004 tests (kept out of 'builders' on purpose)."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Shift
from plant_monitor.domain.notices import (
    ActiveCaseRow,
    Notice,
    NoticeType,
    Origin,
    Reason,
    ShiftReport,
    notice_id_for,
)
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds

from builders import combination_of, released_payload, snapshot_payload, unit_payload, write_snapshot

SEDAN_LOCAL_CASE = "S001-Sedán-Local"
SUV_LOCAL_CASE = "S002-SUV-Local"
PICKUP_LOCAL_CASE = "S001-Pickup-Local"
PICKUP_BRAZIL_CASE = "S001-Pickup-Brasil"


def make_notice(
    snapshot_id: str,
    tipo: NoticeType,
    case_id: str,
    *,
    severity: Severity,
    state: CaseState,
    texto: str | None = None,
    stage: Stage | None = Stage.ASSEMBLY,
) -> Notice:
    """A valid notice; 'motivo' is 'gap' unless the severity is 'ninguna'."""
    combo = combination_of(case_id)
    notice_id = notice_id_for(snapshot_id, tipo, case_id)
    return Notice(
        notice_id=notice_id,
        snapshot_id=snapshot_id,
        case_id=case_id,
        modelo=combo.modelo,
        mercado=combo.mercado,
        tipo=tipo,
        severidad=severity,
        severidad_maxima=severity,
        estado=state,
        origen=Origin.THRESHOLD,
        motivo=() if severity is Severity.NONE else (Reason.GAP,),
        causa=Cause(categoria=CauseCategory.UNDECLARED, etapa=stage),
        evidencia=(),
        texto=texto if texto is not None else f"{combo.modelo} / {combo.mercado}: {notice_id}",
    )


def alert_notice(snapshot_id: str, case_id: str, *, texto: str | None = None) -> Notice:
    """An 'alerta_inmediata' notice: 'escalado' and 'critica'."""
    return make_notice(
        snapshot_id,
        NoticeType.ALERT,
        case_id,
        severity=Severity.CRITICAL,
        state=CaseState.ESCALATED,
        texto=texto,
    )


def news_notice(snapshot_id: str, case_id: str) -> Notice:
    """An 'informe_de_turno' notice: 'en_seguimiento' and 'media'."""
    return make_notice(
        snapshot_id, NoticeType.SHIFT_REPORT, case_id, severity=Severity.MEDIUM, state=CaseState.FOLLOW_UP
    )


def silent_notice(snapshot_id: str, case_id: str) -> Notice:
    """A 'sin_aviso' notice: 'en_seguimiento' and 'media'."""
    return make_notice(
        snapshot_id, NoticeType.NO_NOTICE, case_id, severity=Severity.MEDIUM, state=CaseState.FOLLOW_UP
    )


def active_row(case_id: str) -> ActiveCaseRow:
    """A 'casos_activos' row: 'en_seguimiento' and 'media'."""
    combo = combination_of(case_id)
    return ActiveCaseRow(
        case_id=case_id,
        modelo=combo.modelo,
        mercado=combo.mercado,
        gap_unidades=-4.0,
        gap_pct=-13.3,
        retraso_dias=0.0,
        severidad=Severity.MEDIUM,
        severidad_maxima=Severity.MEDIUM,
        estado=CaseState.FOLLOW_UP,
        etapa_cuello=Stage.ASSEMBLY,
    )


def shift_report(
    turno_id: str, snapshot_id: str, news: Sequence[str] = (), active: Sequence[str] = ()
) -> ShiftReport:
    """A report whose 'novedades' and 'casos_activos' are built from case ids."""
    return ShiftReport(
        turno_id=turno_id,
        snapshot_id=snapshot_id,
        novedades=tuple(news_notice(snapshot_id, case_id) for case_id in news),
        casos_activos=tuple(active_row(case_id) for case_id in active),
    )


# --- E41 series: two shifts (plus a third for E42) over the fixture plant ---

FIXTURE_PLANT = Path(__file__).resolve().parent / "fixtures" / "plant"
SERIES_HEADERS: dict[str, tuple[str, str]] = {
    "S001": ("2026-03-02T10:00", "T01"),
    "S002": ("2026-03-02T14:00", "T01"),
    "S003": ("2026-03-02T18:00", "T02"),
    "S004": ("2026-03-02T22:00", "T02"),
    "S005": ("2026-03-03T02:00", "T03"),
    "S006": ("2026-03-03T06:00", "T03"),
}
type Releases = dict[tuple[Model, Market], int]
SERIES_RELEASES: dict[str, Releases] = {
    "S001": {
        (Model.PICKUP, Market.LOCAL): 1,
        (Model.SUV, Market.LOCAL): 2,
        (Model.SEDAN, Market.BRAZIL): 24,
        (Model.SEDAN, Market.EUROPE): 12,
        (Model.SUV, Market.BRAZIL): 18,
        (Model.SUV, Market.EUROPE): 30,
        (Model.PICKUP, Market.EUROPE): 12,
    },
    "S002": {(Model.PICKUP, Market.LOCAL): 5, (Model.PICKUP, Market.BRAZIL): 10},
    "S003": {(Model.PICKUP, Market.LOCAL): 2, (Model.SUV, Market.LOCAL): 4, (Model.PICKUP, Market.BRAZIL): 5},
    "S004": {(Model.PICKUP, Market.LOCAL): 8, (Model.SUV, Market.LOCAL): 4, (Model.PICKUP, Market.BRAZIL): 5},
    "S005": {},
    "S006": {},
}


def plant_context() -> PlantContext:
    """Plant context from the fixture CSVs and 'umbrales.yaml'."""
    shifts = load_shifts(FIXTURE_PLANT / "turnos.csv")
    return PlantContext(
        plan=load_plan(FIXTURE_PLANT / "plan_produccion.csv", shifts),
        shifts=shifts,
        standards=StandardsTable.from_rows(load_standards(FIXTURE_PLANT / "tiempos_estandar.csv")),
        shipments=ShipmentsTable.from_rows(load_shipments(FIXTURE_PLANT / "embarques.csv")),
        thresholds=load_thresholds(FIXTURE_PLANT / "umbrales.yaml"),
    )


def plant_shifts() -> list[Shift]:
    """Fixture 'turnos.csv': T01-T03 over S001-S006."""
    return load_shifts(FIXTURE_PLANT / "turnos.csv")


def series_snapshot(snapshot_id: str) -> dict[str, object]:
    """Payload of one series snapshot: releases per 'SERIES_RELEASES', one Pickup-Brasil unit at S001."""
    timestamp, turno = SERIES_HEADERS[snapshot_id]
    hour = (datetime.fromisoformat(timestamp) - timedelta(hours=1)).isoformat(timespec="minutes")
    released = [
        released_payload(
            unidad_id=f"{snapshot_id}-{model[:2]}-{market[:2]}-{n:02d}",
            modelo=str(model),
            mercado=str(market),
            hora=hour,
        )
        for (model, market), count in SERIES_RELEASES[snapshot_id].items()
        for n in range(1, count + 1)
    ]
    in_plant = (
        [
            unit_payload(
                unidad_id="U-PB-001",
                modelo="Pickup",
                mercado="Brasil",
                etapa="montaje",
                ingreso_etapa="2026-03-01T20:00",
                retrabajos=0,
                embarque_asignado="BRA-0303",
            )
        ]
        if snapshot_id == "S001"
        else []
    )
    return snapshot_payload(in_plant, released, snapshot_id=snapshot_id, timestamp=timestamp, turno=turno)


def write_series(directory: Path, snapshot_ids: Sequence[str]) -> list[Arrival]:
    """Write the named snapshots under 'directory' and return their arrivals in the given order."""
    directory.mkdir(parents=True, exist_ok=True)
    arrivals: list[Arrival] = []
    for orden, snapshot_id in enumerate(snapshot_ids, start=1):
        path = write_snapshot(directory, series_snapshot(snapshot_id), f"{snapshot_id}.json")
        received = datetime.fromisoformat(SERIES_HEADERS[snapshot_id][0])
        arrivals.append(Arrival(orden=orden, snapshot_id=snapshot_id, archivo=path, recibido=received))
    return arrivals
