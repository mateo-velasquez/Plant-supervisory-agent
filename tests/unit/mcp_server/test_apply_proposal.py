"""009 T11: 'apply_proposal' through the in-process client (R11, E9)."""

import json
from dataclasses import replace

import pytest
from agent_builders import RAISE5, lift_proposal, validated
from incident_runs import AC1, EV_T05, F3, PICKUP_ANY
from judgment_builders import (
    AC2,
    PB_CASE,
    PL_CASE,
    FakeJudgment,
    bare_frame,
    incident_tool_context,
    result_of,
)

from plant_monitor.cases.ledger import DuplicateRaise, LiftNotLater
from plant_monitor.domain.causes import CauseCategory, CauseScope, Evidence
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.context import JudgmentResult, ProposalBook, SnapshotFrame
from plant_monitor.mcp_server.server import build_server

from notice_builders import alert_notice

pytestmark = pytest.mark.anyio

P1 = "S010-p1"


class DuplicatingJudgment(FakeJudgment):
    """A judgment writer whose raise is refused by the ledger as a duplicate."""

    def raise_severity(
        self, categoria: CauseCategory, scope: CauseScope, evidence: Evidence
    ) -> JudgmentResult:
        """Refuse like the ledger."""
        raise DuplicateRaise(AC2, scope)


def err(message: str) -> str:
    """The text a refusal of 'apply_proposal' arrives with."""
    return f"Error executing tool apply_proposal: {message}"


def frame_with(writer: FakeJudgment | None, book: ProposalBook | None) -> SnapshotFrame:
    """An S010 frame with the writer in its three slots and the book, either optional."""
    base = bare_frame("S010")
    if writer is None:
        return base
    return SnapshotFrame.with_writer(base.snapshot_id, base.at, base.metrics, base.units, writer, book)


async def apply_in(frame: SnapshotFrame, *ids: str) -> list[tuple[str, bool]]:
    """Call 'apply_proposal' once per id inside 'frame'; return '(text, is_error)' of each."""
    ctx, frames = incident_tool_context()
    results: list[tuple[str, bool]] = []
    with frames.entered(frame):
        async with ToolClient(build_server(ctx, frames, tools=("apply_proposal",))) as client:
            for proposal_id in ids:
                outcome = await client.call("apply_proposal", {"propuesta": proposal_id})
                results.append((outcome.text, outcome.is_error))
    return results


def new_book() -> ProposalBook:
    """A book holding 'S010-p1' (the raise of the Pickup stop)."""
    return ProposalBook([validated(P1, RAISE5)])


async def test_e9a_an_unknown_id_is_refused_and_reaches_no_writer() -> None:
    """E9 (a): 'S010-p9' is not in the book; the writer is never called."""
    writer = FakeJudgment()
    assert await apply_in(frame_with(writer, new_book()), "S010-p9") == [
        (err("unknown proposal S010-p9 at S010"), True)
    ]
    assert writer.calls == []


async def test_e9d_a_frame_with_no_book_refuses_every_proposal() -> None:
    """E9 (d): no book on the frame is the 'no proposals are being applied' refusal."""
    writer = FakeJudgment()
    frame = replace(bare_frame("S010"), raises=writer)
    assert await apply_in(frame, P1) == [(err("no proposals are being applied at this snapshot"), True)]
    assert writer.calls == []


async def test_e9bc_a_proposal_calls_the_raise_writer_once_and_cannot_be_applied_twice() -> None:
    """E9 (b), (c): one 'raise_severity' with the proposal's own fields; the repeat is refused."""
    changed = alert_notice("S010", PL_CASE)
    writer = FakeJudgment(
        result_of(case_ids=(PL_CASE, PB_CASE), active_cause_id=AC2, changed=(changed,), pending=("n-1",))
    )
    book = new_book()
    first, second = await apply_in(frame_with(writer, book), P1, P1)
    assert not first[1]
    assert writer.calls == [("raise_severity", CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05)]
    result = json.loads(first[0])
    assert set(result) == {"propuesta", "causa_activa", "casos", "avisos", "pendientes"}
    assert (result["propuesta"], result["causa_activa"], result["casos"]) == (P1, AC2, [PL_CASE, PB_CASE])
    assert result["pendientes"] == ["n-1"]
    assert book.applied() == (P1,)
    assert second == (err(f"proposal {P1} is already applied"), True)


async def test_risk_a_validated_proposal_with_a_fragment_not_in_the_logbook_is_refused_at_apply() -> None:
    """Risk: a refactor drops the re-verification and a stale quote reaches the writer."""
    writer = FakeJudgment()
    book = ProposalBook([validated(P1, {**RAISE5, "fragmento": "se detuvo la línea de montaje de Pickup"})])
    assert await apply_in(frame_with(writer, book), P1) == [(err("fragment not found in T05"), True)]
    assert writer.calls == []
    assert book.applied() == ()


class LaterLogbookJudgment(FakeJudgment):
    """A judgment writer whose lift is refused by the ledger as not later than the opening logbook."""

    def lift(self, active_cause_id: str, evidence: Evidence) -> JudgmentResult:
        """Refuse like the ledger."""
        raise LiftNotLater("T03", "T03", active_cause_id)


async def test_risk_a_lift_refused_for_its_logbook_comes_back_unchanged_and_stays_unapplied() -> None:
    """Risk: the lift refusal of the 008 ledger is rewrapped or swallowed and the model cannot correct it."""
    book = ProposalBook([validated(P1, lift_proposal(AC1, "T03", F3, "resuelta"))])
    refusal = f"T03 is not later than T03, which opened active cause {AC1}"
    assert await apply_in(frame_with(LaterLogbookJudgment(), book), P1) == [(err(refusal), True)]
    assert book.applied() == ()


async def test_e9e_a_ledger_refusal_reaches_the_model_unchanged_and_leaves_the_proposal_unapplied() -> None:
    """E9 (e): the duplicate-raise text comes back as is; 'applied()' stays empty."""
    book = new_book()
    refusal = "active cause S010-causa-1 already covers Pickup in montaje, any market"
    assert await apply_in(frame_with(DuplicatingJudgment(), book), P1) == [(err(refusal), True)]
    assert book.applied() == ()
