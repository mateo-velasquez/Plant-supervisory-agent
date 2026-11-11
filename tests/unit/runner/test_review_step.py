"""009 T15a: 'InvestigatorStep' over FakeModel, IF logbooks and an in-memory registry (E25)."""

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from agent_builders import RAISE5, out, set_cause_proposal, tool, validated
from incident_builders import (
    INCIDENTS,
    copy_incident_logbooks,
    incident_shifts,
    incident_snapshot,
)
from incident_runs import F5, Act, IncidentRun, incident_run
from judgment_builders import PL_CASE, incident_tool_context
from mcp.server.mcpserver import MCPServer

from plant_monitor.agents.factory import INVESTIGATOR_TOOLS, build_investigator
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.investigator import ReviewLog
from plant_monitor.agents.loop import LoopLog, LoopOutcome, ToolPort
from plant_monitor.agents.model import ModelReply, ModelRequest, TextBlock
from plant_monitor.cases.notice_builder import SnapshotNotices
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.reviews import LogbookReview, ReviewMark
from plant_monitor.config import Settings
from plant_monitor.domain.calendar import snapshot_position
from plant_monitor.domain.models import Snapshot, SnapshotCommit
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import build_server
from plant_monitor.runner.pipeline import SnapshotDecision
from plant_monitor.runner.review_step import InvestigatorStep

from builders import isolate_settings_env
from notice_builders import alert_notice

REVIEWED_BEFORE = {2: "T01", 4: "T02", 6: "T03", 8: "T04"}
S010_P1 = "S010-p1"


@dataclass
class Rig:
    """The step under test, its model and registry, and the S010 decision inside 'processing'."""

    step: InvestigatorStep
    model: FakeModel
    registry: SqliteRegistry
    decision: SnapshotDecision


def tool_factory(server: MCPServer) -> Callable[[], AbstractAsyncContextManager[ToolPort]]:
    """The tool client opener the investigator takes, annotated once."""
    return lambda: ToolClient(server)


def mark_reviewed(run: IncidentRun, turno_id: str) -> Act:
    """An 'act' that stores T0n as reviewed at the snapshot being processed."""

    def act(decision: SnapshotDecision) -> SnapshotDecision:
        sid = decision.snapshot.snapshot_id
        review = LogbookReview(
            turno_id=turno_id, attempts=1, last_attempt_at=sid, reviewed_at=sid, given_up_at=None
        )
        run.registry.reviews.save(review)
        return decision

    return act


@contextmanager
def s010_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: Sequence[ModelReply | Exception],
    logbooks: Path = INCIDENTS / "bitacoras",
) -> Iterator[Rig]:
    """IF to S009 with T01-T04 reviewed, then S010 decided inside its unit of work."""
    isolate_settings_env(monkeypatch, tmp_path)
    settings = Settings(anthropic_api_key="k")
    ctx, frames = incident_tool_context(logbooks)
    model = FakeModel(script)
    server = build_server(ctx, frames, tools=INVESTIGATOR_TOOLS)
    investigator = build_investigator(settings, model, tool_factory(server))
    with incident_run() as run:
        for number in range(1, 10):
            turno = REVIEWED_BEFORE.get(number)
            run.step(number, None if turno is None else mark_reviewed(run, turno))
        snapshot = Snapshot.model_validate(incident_snapshot("S010"))
        shift, position = snapshot_position(incident_shifts(), "S010")
        with run.registry.processing(SnapshotCommit("S010", "hash-S010", (), {})):
            decision = run.pipeline.decide(snapshot, shift, position)
            step = InvestigatorStep(
                investigator,
                frames,
                ctx.logbooks,
                run.registry.reviews,
                settings.logbook_review_max_attempts,
                settings.proposal_output_max_chars,
            )
            yield Rig(step, model, run.registry, decision)


def marks_of(marks: Mapping[str, ReviewMark]) -> dict[str, str]:
    """The marks as plain strings."""
    return {turno: mark.value for turno, mark in marks.items()}


@pytest.mark.parametrize(
    ("coordinator", "applied", "mark"),
    [
        pytest.param(LoopOutcome.DONE, (), "revisada", id="a-coordinator-done"),
        pytest.param(LoopOutcome.MISSING_TEXTS, (S010_P1,), "revisada", id="d-fallback-all-applied"),
        pytest.param(LoopOutcome.MISSING_TEXTS, (), "reintento", id="e-fallback-none-applied"),
    ],
)
def test_e25_a_d_e_a_valid_output_is_marked_after_the_coordinator_and_nothing_is_written_before(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    coordinator: LoopOutcome,
    applied: tuple[str, ...],
    mark: str,
) -> None:
    """E25 (a), (d), (e), Q-53: one request, 'S010-p1' accepted; the mark follows what the coordinator did."""
    with s010_rig(tmp_path, monkeypatch, [out(RAISE5)]) as rig:
        plan = rig.step.plan(rig.decision)
        assert (plan.present, plan.missing) == (("T05",), ())
        outcome = rig.step.run(plan, rig.decision, LoopLog(), ReviewLog())
        assert len(rig.model.requests) == 1
        assert [p.id for p in outcome.accepted] == [S010_P1]
        assert rig.registry.reviews.get(["T05"]) == {}
        marks = rig.step.record(outcome, coordinator, "S010", applied=applied)
        assert marks_of(marks) == {"T05": mark}


def test_e25_b_two_rejected_outputs_fall_back_with_no_proposal_and_a_retry_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E25 (b): 2 requests, 'fallback:invalid_output', 2 rejections logged, accepted '()', 'reintento'."""
    bad = out(set_cause_proposal(PL_CASE, "no_declarada", "T05", F5, "activa_sin_fecha"))
    with s010_rig(tmp_path, monkeypatch, [bad, bad]) as rig:
        plan = rig.step.plan(rig.decision)
        review_log = ReviewLog()
        outcome = rig.step.run(plan, rig.decision, LoopLog(), review_log)
        assert len(rig.model.requests) == 2
        assert outcome.outcome is LoopOutcome.INVALID_OUTPUT
        assert outcome.accepted == ()
        assert len(review_log.rejections) == 2
        marks = rig.step.record(outcome, None, "S010", applied=())
        assert marks_of(marks) == {"T05": "reintento"}


def test_risk_a_run_that_does_not_end_done_keeps_no_accepted_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk: a proposal accepted earlier survives a later fallback and is applied (R6)."""
    bad = out(set_cause_proposal(PL_CASE, "no_declarada", "T05", F5, "activa_sin_fecha"))
    with s010_rig(tmp_path, monkeypatch, [bad, bad]) as rig:
        plan = rig.step.plan(rig.decision)
        review_log = ReviewLog(accepted=(validated(S010_P1, RAISE5),))
        outcome = rig.step.run(plan, rig.decision, LoopLog(), review_log)
        assert outcome.outcome is LoopOutcome.INVALID_OUTPUT
        assert outcome.accepted == ()


ALL_REVIEWED = ["T01", "T02", "T03", "T04", "T05"]
NOT_SET_CAUSE = "propuestas[0]: only set_cause is proposed when looking up a cause; got raise"
GET_T05 = tool("get_logbook", {"turno_id": "T05"})
PL_CAUSE = set_cause_proposal(PL_CASE, "parada_de_linea", "T05", F5, "activa_sin_fecha")


def lookup_decision(rig: Rig, cited: frozenset[str] = frozenset()) -> SnapshotDecision:
    """The S010 decision with one required alert for PL, as a mid snapshot would give (R2b)."""
    notices = SnapshotNotices((alert_notice("S010", PL_CASE),), None, ())
    return replace(rig.decision, notices=notices, cited=cited)


def review_t05(rig: Rig) -> Mapping[str, LogbookReview]:
    """Mark T05 reviewed at S010, so no logbook is pending, and return every stored review."""
    review = LogbookReview(
        turno_id="T05", attempts=1, last_attempt_at="S010", reviewed_at="S010", given_up_at=None
    )
    rig.registry.reviews.save(review)
    return rig.registry.reviews.get(ALL_REVIEWED)


def task_of(request: ModelRequest) -> dict[str, Any]:
    """The compact JSON of the first user message."""
    block = request.messages[0].content[0]
    assert isinstance(block, TextBlock)
    payload: dict[str, Any] = json.loads(block.text.splitlines()[1])
    return payload


def test_e27_a_a_cause_lookup_asks_only_for_the_alert_case_and_writes_no_review_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E27 (a), R2b: 'bitacoras' '[]', 'casos_sin_causa' [PL], 'S010-p1' accepted, reviews untouched."""
    with s010_rig(tmp_path, monkeypatch, [GET_T05, out(PL_CAUSE)]) as rig:
        before = review_t05(rig)
        decision = lookup_decision(rig)
        plan = rig.step.plan(decision)
        assert (plan.present, plan.missing, plan.lookup) == ((), (), (PL_CASE,))
        outcome = rig.step.run(plan, decision, LoopLog(), ReviewLog())
        task = task_of(rig.model.requests[0])
        assert (task["bitacoras"], [c["case_id"] for c in task["casos_sin_causa"]]) == ([], [PL_CASE])
        assert outcome.outcome is LoopOutcome.DONE
        assert [p.id for p in outcome.accepted] == [S010_P1]
        assert rig.registry.reviews.get(ALL_REVIEWED) == before


def test_e27_b_two_raise_proposals_are_refused_and_the_alert_keeps_no_declarada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E27 (b), R2b, R6: control refuses both raises; 'invalid_output', nothing accepted, no review change."""
    with s010_rig(tmp_path, monkeypatch, [out(RAISE5), out(RAISE5)]) as rig:
        before = review_t05(rig)
        decision = lookup_decision(rig)
        review_log = ReviewLog()
        plan = rig.step.plan(decision)
        outcome = rig.step.run(plan, decision, LoopLog(), review_log)
        assert len(rig.model.requests) == 2
        assert review_log.rejections == [(NOT_SET_CAUSE,), (NOT_SET_CAUSE,)]
        assert (outcome.outcome, outcome.accepted) == (LoopOutcome.INVALID_OUTPUT, ())
        assert rig.registry.reviews.get(ALL_REVIEWED) == before


@pytest.mark.parametrize(
    ("reviewed", "cited"),
    [
        pytest.param(True, frozenset({PL_CASE}), id="alert-case-has-a-cause"),
        pytest.param(False, frozenset(), id="a-review-runs-here"),
    ],
)
def test_e27_c_no_lookup_when_the_case_has_a_cause_or_a_review_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reviewed: bool, cited: frozenset[str]
) -> None:
    """E27 (c), R2b: the plan has no lookup; with nothing pending the step sends no request."""
    with s010_rig(tmp_path, monkeypatch, []) as rig:
        if reviewed:
            review_t05(rig)
        decision = lookup_decision(rig, cited)
        plan = rig.step.plan(decision)
        assert plan.lookup == ()
        assert plan.present == (() if reviewed else ("T05",))
        if reviewed:
            rig.step.run(plan, decision, LoopLog(), ReviewLog())
            assert rig.model.requests == []


def test_r2b_no_lookup_at_a_snapshot_where_no_logbook_is_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2b: an uncited alert at S001, before any shift closed, gives no lookup and no request."""
    isolate_settings_env(monkeypatch, tmp_path)
    settings = Settings(anthropic_api_key="k")
    ctx, frames = incident_tool_context()
    model = FakeModel([])
    server = build_server(ctx, frames, tools=INVESTIGATOR_TOOLS)
    investigator = build_investigator(settings, model, tool_factory(server))
    with incident_run() as run:
        snapshot = Snapshot.model_validate(incident_snapshot("S001"))
        shift, position = snapshot_position(incident_shifts(), "S001")
        with run.registry.processing(SnapshotCommit("S001", "hash-S001", (), {})):
            decision = run.pipeline.decide(snapshot, shift, position)
            step = InvestigatorStep(
                investigator,
                frames,
                ctx.logbooks,
                run.registry.reviews,
                settings.logbook_review_max_attempts,
                settings.proposal_output_max_chars,
            )
            notices = SnapshotNotices((alert_notice("S001", PL_CASE),), None, ())
            alerting = replace(decision, notices=notices, cited=frozenset())
            plan = step.plan(alerting)
            assert (plan.present, plan.missing, plan.lookup) == ((), (), ())
            step.run(plan, alerting, LoopLog(), ReviewLog())
            assert model.requests == []


def test_risk_a_lookup_beside_a_missing_logbook_adds_no_mark_and_keeps_the_failed_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk: R2b with R8: the lookup run must not turn the missing T05 into a review or a second attempt."""
    logbooks = copy_incident_logbooks(tmp_path / "bitacoras", omit=("T05",))
    with s010_rig(tmp_path, monkeypatch, [out()], logbooks) as rig:
        decision = lookup_decision(rig)
        plan = rig.step.plan(decision)
        assert (plan.present, plan.missing, plan.lookup) == ((), ("T05",), (PL_CASE,))
        outcome = rig.step.run(plan, decision, LoopLog(), ReviewLog())
        assert (outcome.outcome, outcome.accepted) == (LoopOutcome.DONE, ())
        assert marks_of(rig.step.record(outcome, None, "S010")) == {"T05": "reintento"}
        assert rig.registry.reviews.get(["T05"])["T05"].attempts == 1


def test_e25_c_a_missing_logbook_sends_no_request_and_gets_a_retry_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E25 (c), R8: plan missing [T05], present '()'; the model is not called; 'reintento'."""
    logbooks = copy_incident_logbooks(tmp_path / "bitacoras", omit=("T05",))
    with s010_rig(tmp_path, monkeypatch, [], logbooks) as rig:
        plan = rig.step.plan(rig.decision)
        assert (plan.present, plan.missing) == ((), ("T05",))
        outcome = rig.step.run(plan, rig.decision, LoopLog(), ReviewLog())
        assert rig.model.requests == []
        assert outcome.ran is False
        marks = rig.step.record(outcome, None, "S010", applied=())
        assert marks_of(marks) == {"T05": "reintento"}
