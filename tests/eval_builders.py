"""Synthetic builders for 005 evaluator tests: alerts, news, rows, reports and the E40 registry."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.models import Shift, SnapshotCommit
from plant_monitor.domain.notices import (
    ActiveCaseRow,
    Notice,
    NoticeType,
    Origin,
    Reason,
    ShiftReport,
    notice_id_for,
)
from plant_monitor.evaluation.output import RunOutput
from plant_monitor.ingestion.plant import load_shifts

from builders import FIXTURE_PLANT, combination_of

if TYPE_CHECKING:
    from plant_monitor.evaluation.golden import GoldenSet

SEL = "S001-Sedán-Local"
PL = "S001-Pickup-Local"
DELIVERED_AT = datetime(2026, 3, 2, 14, 30, tzinfo=UTC)


def _notice(
    snapshot_id: str,
    tipo: NoticeType,
    case_id: str,
    estado: CaseState,
    severidad: Severity,
    maxima: Severity | None,
) -> Notice:
    combo = combination_of(case_id)
    notice_id = notice_id_for(snapshot_id, tipo, case_id)
    return Notice(
        notice_id=notice_id,
        snapshot_id=snapshot_id,
        case_id=case_id,
        modelo=combo.modelo,
        mercado=combo.mercado,
        tipo=tipo,
        severidad=severidad,
        severidad_maxima=severidad if maxima is None else maxima,
        estado=estado,
        origen=Origin.THRESHOLD,
        motivo=() if severidad is Severity.NONE else (Reason.GAP,),
        causa=Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY),
        evidencia=(),
        texto=f"{combo.modelo} / {combo.mercado}: {notice_id}",
    )


def alert(snapshot_id: str, case_id: str = SEL) -> Notice:
    """An 'alerta_inmediata' notice ('escalado', 'critica')."""
    return _notice(
        snapshot_id, NoticeType.ALERT, case_id, CaseState.ESCALATED, Severity.CRITICAL, Severity.CRITICAL
    )


def news(
    snapshot_id: str,
    case_id: str = SEL,
    estado: CaseState = CaseState.FOLLOW_UP,
    severidad: Severity = Severity.MEDIUM,
    maxima: Severity | None = None,
    tipo: NoticeType = NoticeType.SHIFT_REPORT,
) -> Notice:
    """A notice of 'tipo' (default 'informe_de_turno') with the given state and severities."""
    return _notice(snapshot_id, tipo, case_id, estado, severidad, maxima)


def row(
    case_id: str = SEL,
    estado: CaseState = CaseState.FOLLOW_UP,
    severidad: Severity = Severity.MEDIUM,
    maxima: Severity | None = None,
) -> ActiveCaseRow:
    """A 'casos_activos' row for the case."""
    combo = combination_of(case_id)
    return ActiveCaseRow(
        case_id=case_id,
        modelo=combo.modelo,
        mercado=combo.mercado,
        gap_unidades=-4.0,
        gap_pct=-13.3,
        retraso_dias=0.0,
        severidad=severidad,
        severidad_maxima=severidad if maxima is None else maxima,
        estado=estado,
        etapa_cuello=Stage.ASSEMBLY,
    )


def report(
    turno_id: str,
    snapshot_id: str,
    novedades: Sequence[Notice] = (),
    rows: Sequence[ActiveCaseRow] = (),
) -> ShiftReport:
    """A shift report from ready-made news items and rows."""
    return ShiftReport(
        turno_id=turno_id, snapshot_id=snapshot_id, novedades=tuple(novedades), casos_activos=tuple(rows)
    )


# --- E40 registry: S001 to S004 on the fixture calendar ---

E40_ALERT = alert("S003", SEL)
E40_T01 = report(
    "T01",
    "S002",
    (news("S002", SEL, severidad=Severity.HIGH), news("S002", PL)),
    (row(SEL, severidad=Severity.HIGH), row(PL)),
)
E40_T02 = report(
    "T02",
    "S004",
    (news("S004", SEL, CaseState.ESCALATED, Severity.CRITICAL),),
    (row(SEL, CaseState.ESCALATED, Severity.CRITICAL), row(PL)),
)


def _commit(snapshot_id: str) -> SnapshotCommit:
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


def write_e40_registry(path: Path) -> None:
    """Write E40's four snapshots through 'SqliteRegistry', mark 'T01-informe' delivered and close it."""
    mid = (news("S001", SEL), news("S001", PL))
    s002 = (news("S002", SEL, severidad=Severity.HIGH), news("S002", PL))
    s003 = (E40_ALERT, news("S003", PL, tipo=NoticeType.NO_NOTICE))
    s004 = (
        news("S004", SEL, CaseState.ESCALATED, Severity.CRITICAL),
        news("S004", PL, tipo=NoticeType.NO_NOTICE),
    )
    with SqliteRegistry(path) as registry:
        with registry.processing(_commit("S001")):
            registry.notices.save("S001", mid, None)
        with registry.processing(_commit("S002")):
            registry.notices.save("S002", s002, E40_T01)
        with registry.processing(_commit("S003")):
            registry.notices.save("S003", s003, None)
        with registry.processing(_commit("S004")):
            registry.notices.save("S004", s004, E40_T02)
        registry.notices.mark_delivered("T01-informe", DELIVERED_AT)


# --- golden items: plain dicts written as YAML, so tests can break any field ---

type Item = dict[str, object]

JUSTIFICATION = "§4 synthetic golden item"


def fixture_shifts() -> list[Shift]:
    """The fixture calendar (T01 to T03)."""
    return load_shifts(FIXTURE_PLANT / "turnos.csv")


def case_key(case_id: str) -> Item:
    """The golden 'case' mapping for a case id such as 'S001-Sedán-Local'."""
    combo = combination_of(case_id)
    return {"modelo": combo.modelo.value, "mercado": combo.mercado.value, "abre_en": case_id.split("-")[0]}


def _item(fields: Item, drop: Sequence[str], overrides: Item) -> Item:
    item: Item = {"justification": JUSTIFICATION, **fields, **overrides}
    for key in drop:
        del item[key]
    return item


def golden_alert(
    case_id: str = SEL, snapshot_id: str = "S003", *, drop: Sequence[str] = (), **fields: object
) -> Item:
    """An expected alert; 'fields' override or add keys and 'drop' removes keys."""
    return _item({"case": case_key(case_id), "snapshot_id": snapshot_id}, drop, fields)


def golden_news(
    turno_id: str,
    case_id: str = SEL,
    estado: str = "en_seguimiento",
    severidad: str = "alta",
    maxima: str = "alta",
    *,
    drop: Sequence[str] = (),
    **fields: object,
) -> Item:
    """An expected news item; 'fields' override or add keys and 'drop' removes keys."""
    base: Item = {
        "turno_id": turno_id,
        "case": case_key(case_id),
        "estado": estado,
        "severidad": severidad,
        "severidad_maxima": maxima,
    }
    return _item(base, drop, fields)


def golden_evidence(bitacora: str, fragmento: str) -> Item:
    """An 'evidencia' mapping."""
    return {"bitacora": bitacora, "fragmento": fragmento}


def golden_cause(
    case_id: str = SEL,
    notice: str = "alerta_inmediata",
    categoria: str = "no_declarada",
    etapa: str | None = None,
    *,
    drop: Sequence[str] = (),
    **fields: object,
) -> Item:
    """An expected cause; 'fields' override or add keys and 'drop' removes keys."""
    base: Item = {"case": case_key(case_id), "notice": notice, "categoria": categoria, "etapa": etapa}
    return _item(base, drop, fields)


def golden_file(
    covers: Sequence[str],
    *,
    alerts: Sequence[Item] = (),
    news: Sequence[Item] = (),
    causes: Sequence[Item] = (),
) -> Item:
    """A golden file mapping; empty sections are left out."""
    data: Item = {"covers": list(covers)}
    for name, items in (("alerts", alerts), ("news", news), ("causes", causes)):
        if items:
            data[name] = list(items)
    return data


def write_golden(directory: Path, name: str, content: object) -> Path:
    """Write 'content' as UTF-8 YAML (a str is written as is) and return the path."""
    path = directory / name
    text = (
        content if isinstance(content, str) else yaml.safe_dump(content, allow_unicode=True, sort_keys=False)
    )
    path.write_text(text, encoding="utf-8")
    return path


# --- run and golden objects for scoring tests (005 T8-T11) ---

SL2 = "S002-SUV-Local"
SL3 = "S003-SUV-Local"
SL5 = "S005-SUV-Local"
SE3 = "S003-SUV-Europa"
PB1 = "S001-Pickup-Brasil"
PB3 = "S003-Pickup-Brasil"
PB4 = "S004-Pickup-Brasil"


def run_output(alerts: Sequence[Notice] = (), reports: Sequence[ShiftReport] = ()) -> RunOutput:
    """A 'RunOutput' from ready-made alerts and reports."""
    return RunOutput(alerts=tuple(alerts), reports=tuple(reports))


def _label(section: str, index: int, item: Item) -> str:
    return f"g.yaml#{item['id']}" if "id" in item else f"g.yaml#{section}[{index}]"


def golden_set(
    covers: Sequence[str],
    *,
    alerts: Sequence[Item] = (),
    news: Sequence[Item] = (),
    causes: Sequence[Item] = (),
) -> GoldenSet:
    """A 'GoldenSet' built through the golden models; labels are 'g.yaml#<id>' or 'g.yaml#<section>[<i>]'."""
    from plant_monitor.evaluation.golden import (
        ExpectedAlert,
        ExpectedCause,
        ExpectedNews,
        GoldenSet,
        Labeled,
    )

    return GoldenSet(
        covered_shifts=tuple(covers),
        alerts=tuple(
            Labeled(_label("alerts", i, item), ExpectedAlert.model_validate(item))
            for i, item in enumerate(alerts)
        ),
        news=tuple(
            Labeled(_label("news", i, item), ExpectedNews.model_validate(item)) for i, item in enumerate(news)
        ),
        causes=tuple(
            Labeled(_label("causes", i, item), ExpectedCause.model_validate(item))
            for i, item in enumerate(causes)
        ),
    )
