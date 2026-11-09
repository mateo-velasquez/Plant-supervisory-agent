"""Pure scope rules: which cases an active cause reaches (R6)."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from plant_monitor.domain.cases import Case
from plant_monitor.domain.causes import ActiveCause, CauseCategory, CauseScope, CitedCause
from plant_monitor.domain.enums import Stage
from plant_monitor.domain.models import Combination


@dataclass(frozen=True)
class Candidate:
    """A case with its Q-32 bottleneck stage."""

    case: Case
    stage: Stage | None


def matches(scope: CauseScope, combination: Combination, stage: Stage | None) -> bool:
    """Same model, market (or any) and stage; a case without a bottleneck stage is not excluded."""
    return (
        scope.modelo == combination.modelo
        and (scope.mercado is None or scope.mercado == combination.mercado)
        and (stage is None or stage == scope.etapa)
    )


def same_cause(cited: CitedCause, categoria: CauseCategory, etapa: Stage) -> bool:
    return cited.categoria == categoria and cited.etapa == etapa


def link_targets(
    cause: ActiveCause,
    candidates: Sequence[Candidate],
    cited: Mapping[str, CitedCause],
    linked: Collection[str],
) -> tuple[str, ...]:
    """Matching candidates not yet linked, skipping those with a different cited cause."""
    targets: list[str] = []
    for candidate in candidates:
        case_id = candidate.case.case_id
        if case_id in linked or not matches(cause.scope, candidate.case.combination, candidate.stage):
            continue
        current = cited.get(case_id)
        if current is None or same_cause(current, cause.categoria, cause.scope.etapa):
            targets.append(case_id)
    return tuple(targets)
