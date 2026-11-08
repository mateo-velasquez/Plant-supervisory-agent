"""Golden set: expected alerts, news and causes per day, checked on load (005, Q-34, Q-36, Q-38)."""

import re
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
from yaml.constructor import ConstructorError

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.cases import CaseState, case_id_for
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, Shift
from plant_monitor.domain.notices import NoticeType, Reason
from plant_monitor.ingestion.errors import DataLoadError, describe_validation_error
from plant_monitor.ingestion.held_out import check_ids

_GOLDEN_GLOB = "*.yaml"
_CITATION = re.compile(r"\bcriterio \d", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


class Capability(StrEnum):
    """What a run can produce beyond thresholds; closed set (Q-34)."""

    AGENT = "agent"


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a mapping with a repeated key instead of overwriting it."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        self.flatten_mapping(node)
        seen: set[str] = set()
        for key_node, _ in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                if key_node.value in seen:
                    raise ConstructorError(
                        None, None, f"found duplicate key {key_node.value!r}", key_node.start_mark
                    )
                seen.add(key_node.value)
        return super().construct_mapping(node, deep=deep)


def _cites_rule(value: str) -> str:
    """Stripped text that is non-blank and cites a rule as 'criterio <n>'."""
    stripped = value.strip()
    if not stripped or _CITATION.search(stripped) is None:
        raise ValueError("justification must be non-blank and cite a rule as 'criterio <n>'")
    return stripped


type SnapshotId = Annotated[StrictStr, StringConstraints(pattern=r"^S\d{3}$")]
type ShiftId = Annotated[StrictStr, StringConstraints(pattern=r"^T\d{2}$")]
type QuestionId = Annotated[StrictStr, StringConstraints(pattern=r"^Q-\d{2,}$")]
type ItemId = Annotated[StrictStr, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
type Justification = Annotated[StrictStr, AfterValidator(_cites_rule)]
type Fragment = Annotated[StrictStr, StringConstraints(min_length=1)]


class GoldenModel(BaseModel):
    """Base of every golden model: frozen, extra keys forbidden; strictness is per field."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class CaseKey(GoldenModel):
    """A case as written in a golden file: model, market and opening snapshot."""

    modelo: Model
    mercado: Market
    abre_en: SnapshotId

    @property
    def case_id(self) -> str:
        """The system's case id, as 'case_id_for' builds it."""
        return case_id_for(self.abre_en, Combination(modelo=self.modelo, mercado=self.mercado))


class GoldenItem(GoldenModel):
    """Fields every golden item shares; 'depends_on' only tracks, 'requires' gates (Q-34)."""

    justification: Justification
    id: ItemId | None = None
    depends_on: tuple[QuestionId, ...] = ()
    requires: tuple[Capability, ...] = ()

    @field_validator("depends_on", "requires")
    @classmethod
    def _unique(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if len(set(value)) != len(value):
            raise ValueError("entries must be unique")
        return value


class ExpectedAlert(GoldenItem):
    """An 'alerta_inmediata' expected for a case at a snapshot."""

    case: CaseKey
    snapshot_id: SnapshotId
    motivo: tuple[Reason, ...] | None = None


class ExpectedNews(GoldenItem):
    """An 'informe_de_turno' news item expected for a case in a shift."""

    turno_id: ShiftId
    case: CaseKey
    estado: CaseState
    severidad: Severity
    severidad_maxima: Severity

    @model_validator(mode="after")
    def _check_severities(self) -> Self:
        if self.severidad_maxima < self.severidad:
            raise ValueError("severidad_maxima is below severidad")
        if self.estado is CaseState.RESOLVED and self.severidad is not Severity.NONE:
            raise ValueError("severidad must be ninguna when estado is resuelto")
        return self


class ExpectedEvidence(GoldenModel):
    """A logbook citation: the shift's logbook and a verbatim fragment of it."""

    bitacora: ShiftId
    fragmento: Fragment


class ExpectedCause(GoldenItem):
    """A cause expected on an alert or on a shift's news item; 'evidencia' is required when declared."""

    case: CaseKey
    notice: Literal[NoticeType.ALERT, NoticeType.SHIFT_REPORT]
    turno_id: ShiftId | None = None
    categoria: CauseCategory
    etapa: Stage | None
    evidencia: ExpectedEvidence | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if (self.notice is NoticeType.SHIFT_REPORT) != (self.turno_id is not None):
            raise ValueError("turno_id is required for informe_de_turno and forbidden for alerta_inmediata")
        if (self.categoria is CauseCategory.UNDECLARED) != (self.evidencia is None):
            raise ValueError("evidencia is required for a declared cause and forbidden for no_declarada")
        return self


class GoldenFile(GoldenModel):
    """One golden file: the shifts it covers and its expected items."""

    covers: Annotated[tuple[ShiftId, ...], Field(min_length=1)]
    alerts: tuple[ExpectedAlert, ...] = ()
    news: tuple[ExpectedNews, ...] = ()
    causes: tuple[ExpectedCause, ...] = ()
    notes: str | None = None

    @field_validator("covers")
    @classmethod
    def _unique_covers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("entries must be unique")
        return value


@dataclass(frozen=True)
class Labeled[T: GoldenItem]:
    """A golden item and its label: '<file>#<id>' or '<file>#<section>[<i>]'."""

    label: str
    item: T


@dataclass(frozen=True)
class GoldenSet:
    """All golden items of a directory, with the shifts they cover in calendar order."""

    covered_shifts: tuple[str, ...]
    alerts: tuple[Labeled[ExpectedAlert], ...]
    news: tuple[Labeled[ExpectedNews], ...]
    causes: tuple[Labeled[ExpectedCause], ...]


type LogbookSource = Callable[[frozenset[str]], Mapping[str, str]]


def contains_verbatim(text: str, fragment: str) -> bool:
    """True iff 'fragment' occurs in 'text' with whitespace runs collapsed; case-sensitive (Q-36)."""
    needle = _collapse(fragment)
    return bool(needle) and needle in _collapse(text)


def _collapse(value: str) -> str:
    """'value' with every whitespace run replaced by one space."""
    return _WHITESPACE.sub(" ", value).strip()


@dataclass(frozen=True)
class _Calendar:
    """Calendar order: shifts by 'inicio', each with its mid and closing snapshots (Q-34)."""

    shift_order: tuple[str, ...]
    snapshots: Mapping[str, tuple[str, str]]
    position: Mapping[str, int]

    @classmethod
    def of(cls, shifts: Iterable[Shift]) -> Self:
        """Calendar of 'shifts'."""
        ordered = sorted(shifts, key=lambda shift: shift.inicio)
        snapshots = {shift.turno_id: (shift.snapshot_medio, shift.snapshot_cierre) for shift in ordered}
        order = [snap for pair in snapshots.values() for snap in pair]
        return cls(
            shift_order=tuple(snapshots),
            snapshots=snapshots,
            position={snap: index for index, snap in enumerate(order)},
        )

    def closing(self, turno: str) -> str:
        """Closing snapshot of shift 'turno'."""
        return self.snapshots[turno][1]


@dataclass(frozen=True)
class _Loaded:
    """One parsed and file-checked golden file with its labeled items."""

    name: str
    covers: tuple[str, ...]
    alerts: tuple[Labeled[ExpectedAlert], ...]
    news: tuple[Labeled[ExpectedNews], ...]
    causes: tuple[Labeled[ExpectedCause], ...]


def load_golden(
    directory: Path, shifts: Sequence[Shift], policy: HeldOutPolicy, logbooks: LogbookSource
) -> GoldenSet:
    """Parse, held-out check, file checks, cross-file checks, then golden evidence (one logbooks call)."""
    files = sorted(directory.glob(_GOLDEN_GLOB))
    if not files:
        raise DataLoadError(f"{directory}: no golden .yaml files")
    calendar = _Calendar.of(shifts)
    loaded: list[_Loaded] = []
    for path in files:
        file = _read_file(path)
        _check_file(path.name, file, calendar, policy)
        loaded.append(_label_file(path.name, file))
    _check_across(loaded)
    covered = {shift for entry in loaded for shift in entry.covers}
    golden = GoldenSet(
        covered_shifts=tuple(shift for shift in calendar.shift_order if shift in covered),
        alerts=tuple(item for entry in loaded for item in entry.alerts),
        news=tuple(item for entry in loaded for item in entry.news),
        causes=tuple(item for entry in loaded for item in entry.causes),
    )
    _check_evidence(golden.causes, logbooks)
    return golden


def _read_file(path: Path) -> GoldenFile:
    """Parse one golden file: duplicate keys and non-mapping tops are errors, then the schema."""
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise DataLoadError(f"{path.name}: {error}") from error
    if not isinstance(data, dict):
        raise DataLoadError(f"{path.name}: the top level must be a mapping")
    try:
        return GoldenFile.model_validate(data)
    except ValidationError as error:
        raise DataLoadError(f"{path.name}: {describe_validation_error(error)}") from error


def _check_file(name: str, file: GoldenFile, calendar: _Calendar, policy: HeldOutPolicy) -> None:
    """Held-out refusal first, then calendar, coverage and order checks within one file."""
    check_ids(policy, shifts=_shift_refs(file), snapshots=_snapshot_refs(file), where=name)
    for index, shift in enumerate(file.covers):
        if shift not in calendar.snapshots:
            raise _error(name, f"covers[{index}]", f"{shift} is not in the calendar")
    covered = {snap for shift in file.covers for snap in calendar.snapshots[shift]}
    for index, alert in enumerate(file.alerts):
        where = f"alerts[{index}]"
        opened = _opened_at(name, where, alert.case, calendar)
        if alert.snapshot_id not in covered:
            raise _error(name, f"{where}.snapshot_id", f"{alert.snapshot_id} is not in a covered shift")
        if opened > calendar.position[alert.snapshot_id]:
            raise _error(
                name, f"{where}.abre_en", f"case opens at {alert.case.abre_en}, after the alert snapshot"
            )
    seen_news: dict[tuple[str, str], int] = {}
    for index, news in enumerate(file.news):
        where = f"news[{index}]"
        _require_cover(name, f"{where}.turno_id", news.turno_id, file.covers)
        _opened_at(name, where, news.case, calendar)
        closing = calendar.closing(news.turno_id)
        if calendar.position[news.case.abre_en] > calendar.position[closing]:
            raise _error(name, f"{where}.abre_en", f"case opens at {news.case.abre_en}, after {closing}")
        key = (news.turno_id, news.case.case_id)
        if key in seen_news:
            raise _error(name, where, f"repeats news[{seen_news[key]}] for {news.turno_id} and {key[1]}")
        seen_news[key] = index
    for index, cause in enumerate(file.causes):
        where = f"causes[{index}]"
        _opened_at(name, where, cause.case, calendar)
        if cause.turno_id is not None:
            _require_cover(name, f"{where}.turno_id", cause.turno_id, file.covers)
            if (cause.turno_id, cause.case.case_id) not in seen_news:
                raise _error(name, where, f"no news item for {cause.turno_id} and {cause.case.case_id}")


def _opened_at(name: str, where: str, case: CaseKey, calendar: _Calendar) -> int:
    """Calendar position of the case's opening snapshot; DataLoadError if it is not in the calendar."""
    if case.abre_en not in calendar.position:
        raise _error(name, f"{where}.abre_en", f"{case.abre_en} is not in the calendar")
    return calendar.position[case.abre_en]


def _require_cover(name: str, where: str, shift: str, covers: Sequence[str]) -> None:
    """Raise unless 'shift' is one of the file's 'covers'."""
    if shift not in covers:
        raise _error(name, where, f"{shift} is not in covers")


def _error(name: str, where: str, detail: str) -> DataLoadError:
    """DataLoadError naming the file, the field path and the problem."""
    return DataLoadError(f"{name}: {where}: {detail}")


def _shift_refs(file: GoldenFile) -> list[str]:
    """Every shift id a file names, for the held-out check."""
    refs = list(file.covers)
    refs += [news.turno_id for news in file.news]
    refs += [cause.turno_id for cause in file.causes if cause.turno_id is not None]
    refs += [cause.evidencia.bitacora for cause in file.causes if cause.evidencia is not None]
    return refs


def _snapshot_refs(file: GoldenFile) -> list[str]:
    """Every snapshot id a file names (alert snapshots and case openings), for the held-out check."""
    refs = [alert.snapshot_id for alert in file.alerts]
    refs += [alert.case.abre_en for alert in file.alerts]
    refs += [news.case.abre_en for news in file.news]
    refs += [cause.case.abre_en for cause in file.causes]
    return refs


def _label_file(name: str, file: GoldenFile) -> _Loaded:
    """The file's items with their labels."""
    return _Loaded(
        name=name,
        covers=tuple(file.covers),
        alerts=_labeled(name, "alerts", file.alerts),
        news=_labeled(name, "news", file.news),
        causes=_labeled(name, "causes", file.causes),
    )


def _labeled[T: GoldenItem](name: str, section: str, items: Sequence[T]) -> tuple[Labeled[T], ...]:
    """Items of one section, labeled by id when present, else by position."""
    return tuple(
        Labeled(
            label=f"{name}#{item.id}" if item.id is not None else f"{name}#{section}[{index}]",
            item=item,
        )
        for index, item in enumerate(items)
    )


def _check_across(loaded: Sequence[_Loaded]) -> None:
    """Cross-file checks: one owner per shift, one alert per case, unique ids and causes."""
    owners: dict[str, str] = {}
    for entry in loaded:
        for shift in entry.covers:
            if shift in owners:
                raise DataLoadError(f"{shift} is covered by {owners[shift]} and {entry.name}")
            owners[shift] = entry.name
    alerts = [item for entry in loaded for item in entry.alerts]
    news = [item for entry in loaded for item in entry.news]
    causes = [item for entry in loaded for item in entry.causes]
    ids: dict[str, str] = {}
    for labeled in [*alerts, *news, *causes]:
        if labeled.item.id is not None:
            if labeled.item.id in ids:
                raise DataLoadError(f"duplicate id: {ids[labeled.item.id]} and {labeled.label}")
            ids[labeled.item.id] = labeled.label
    alert_labels: dict[str, str] = {}
    for labeled in alerts:
        case_id = labeled.item.case.case_id
        if case_id in alert_labels:
            raise DataLoadError(f"{case_id}: alerts {alert_labels[case_id]} and {labeled.label}")
        alert_labels[case_id] = labeled.label
    cause_labels: dict[tuple[str, NoticeType, str | None], str] = {}
    for labeled in causes:
        case_id = labeled.item.case.case_id
        if labeled.item.notice is NoticeType.ALERT and case_id not in alert_labels:
            raise DataLoadError(f"{labeled.label}: no alert item for {case_id}")
        key = (case_id, labeled.item.notice, labeled.item.turno_id)
        if key in cause_labels:
            raise DataLoadError(f"{cause_labels[key]} and {labeled.label} are the same cause")
        cause_labels[key] = labeled.label


def _check_evidence(causes: tuple[Labeled[ExpectedCause], ...], logbooks: LogbookSource) -> None:
    """Every golden fragment must appear verbatim in its logbook; the logbooks are read once."""
    cited = {labeled.item.evidencia.bitacora for labeled in causes if labeled.item.evidencia is not None}
    if not cited:
        return
    texts = logbooks(frozenset(cited))
    for labeled in causes:
        evidence = labeled.item.evidencia
        if evidence is not None and not contains_verbatim(
            texts.get(evidence.bitacora, ""), evidence.fragmento
        ):
            raise DataLoadError(f"{labeled.label}: fragment not found in {evidence.bitacora}")
