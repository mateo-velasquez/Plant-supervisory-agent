"""008 helpers: run IF snapshots through 'ThresholdPipeline' with a ledger, raising and lifting causes."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from incident_builders import (
    IncidentScenario,
    incident_context,
    incident_scenario,
    incident_shifts,
    incident_snapshot,
)

from plant_monitor.cases.ledger import CauseLedger
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.calendar import snapshot_position
from plant_monitor.domain.causes import CauseCategory, CauseScope, Evidence
from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import Snapshot, SnapshotCommit
from plant_monitor.runner.pipeline import SnapshotDecision, ThresholdPipeline

F2 = "llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación"
F3 = "El auditor vuelve mañana a primera hora"
F4 = "La auditoría de homologación terminó a las 8:30"
F5 = (
    "se paró la línea de montaje de Pickup por la rotura del transportador aéreo de la estación 3."
    " Mantenimiento espera el repuesto y por ahora no hay fecha confirmada de vuelta"
)
F6 = "la línea de montaje de Pickup volvió a las 4:00"
EV_T02 = Evidence(bitacora="T02", fragmento=F2)
EV_T03 = Evidence(bitacora="T03", fragmento=F3)
EV_T04 = Evidence(bitacora="T04", fragmento=F4)
EV_T05 = Evidence(bitacora="T05", fragmento=F5)
EV_T06 = Evidence(bitacora="T06", fragmento=F6)
PICKUP_ANY = CauseScope(modelo=Model.PICKUP, etapa=Stage.ASSEMBLY, mercado=None)
SUV_EUROPE = CauseScope(modelo=Model.SUV, etapa=Stage.QUALITY, mercado=Market.EUROPE)
SUV_QUALITY_ANY = CauseScope(modelo=Model.SUV, etapa=Stage.QUALITY, mercado=None)
SUV_PAINT_ANY = CauseScope(modelo=Model.SUV, etapa=Stage.PAINT, mercado=None)
AC1 = "S004-causa-1"
AC2 = "S010-causa-1"

type Act = Callable[[SnapshotDecision], SnapshotDecision]


@dataclass
class IncidentRun:
    """One registry, ledger and pipeline over the IF; 'step' runs a snapshot in its own unit of work."""

    registry: SqliteRegistry
    ledger: CauseLedger
    pipeline: ThresholdPipeline
    scenario: IncidentScenario

    def step(self, number: int, act: Act | None = None) -> SnapshotDecision:
        """Decide S<number>, let 'act' write judgment and re-decide, then finish."""
        snapshot_id = f"S{number:03d}"
        shift, position = snapshot_position(incident_shifts(), snapshot_id)
        snapshot = Snapshot.model_validate(incident_snapshot(snapshot_id, self.scenario))
        commit = SnapshotCommit(snapshot_id, f"hash-{snapshot_id}", (), {})
        with self.registry.processing(commit):
            decision = self.pipeline.decide(snapshot, shift, position)
            if act is not None:
                decision = act(decision)
            self.pipeline.finish(decision)
        return decision

    def through(self, last: int, first: int = 1) -> None:
        """Run S<first> to S<last> with no judgment."""
        for number in range(first, last + 1):
            self.step(number)

    def raise_cause(
        self,
        decision: SnapshotDecision,
        categoria: CauseCategory,
        scope: CauseScope,
        evidence: Evidence,
    ) -> SnapshotDecision:
        """Raise through the ledger on the decision's candidates, then re-decide."""
        self.ledger.raise_severity(
            decision.snapshot.snapshot_id, categoria, scope, evidence, decision.candidates
        )
        return self.pipeline.redecide(decision)

    def lift_cause(
        self, decision: SnapshotDecision, active_cause_id: str, evidence: Evidence
    ) -> SnapshotDecision:
        """Lift through the ledger, then re-decide."""
        self.ledger.lift(decision.snapshot.snapshot_id, active_cause_id, evidence)
        return self.pipeline.redecide(decision)


@contextmanager
def incident_run(
    scenario: IncidentScenario | None = None, *, with_ledger: bool = True
) -> Iterator[IncidentRun]:
    """In-memory registry with the IF context; the ledger is omitted when 'with_ledger' is False."""
    ctx = incident_context()
    with SqliteRegistry(":memory:") as registry:
        ledger = CauseLedger(registry.causes, registry.cases, ctx.shifts)
        pipeline = ThresholdPipeline.from_registry(registry, ctx, ledger if with_ledger else None)
        yield IncidentRun(registry, ledger, pipeline, scenario or incident_scenario())
