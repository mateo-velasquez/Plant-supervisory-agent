"""Minimal builders for 007 draft and write-tool tests: spec 004 E37-E41 decisions as 'SnapshotNotices'."""

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime

from plant_monitor.cases.draft import NoticeDraft
from plant_monitor.cases.notice_builder import SnapshotNotices
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory, CauseScope, Evidence
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.notices import Notice, NoticeType
from plant_monitor.mcp_server.context import JudgmentResult, SnapshotFrame
from plant_monitor.runner.pipeline import SnapshotDecision

from notice_builders import (
    PICKUP_BRAZIL_CASE,
    PICKUP_LOCAL_CASE,
    SEDAN_LOCAL_CASE,
    SUV_LOCAL_CASE,
    active_row,
    alert_notice,
    make_notice,
    news_notice,
    shift_report,
    silent_notice,
)

MAX_CHARS = 1500
SUV_SILENT_TEXT = "SUV × Local: sin cambios desde el informe de S002."  # noqa: RUF001


def agent_text(notice_id: str) -> str:
    """The text the spec's examples call 'agent text'."""
    return f"Agente: {notice_id}"


def s001_notices() -> SnapshotNotices:
    """E41 S001: three news decisions at a mid snapshot, no report."""
    cases = (SEDAN_LOCAL_CASE, PICKUP_LOCAL_CASE, PICKUP_BRAZIL_CASE)
    return SnapshotNotices(tuple(news_notice("S001", case) for case in cases), None, ())


def s003_notices() -> SnapshotNotices:
    """E37 / E41 S003: alert, silence and two news at a mid snapshot."""
    decisions = (
        alert_notice("S003", SEDAN_LOCAL_CASE),
        silent_notice("S003", SUV_LOCAL_CASE),
        news_notice("S003", PICKUP_LOCAL_CASE),
        news_notice("S003", PICKUP_BRAZIL_CASE),
    )
    return SnapshotNotices(decisions, None, ())


def s004_notices() -> SnapshotNotices:
    """E41 S004: closing T02 with news SeL, PL, PB and the template silence of SL."""
    silent = make_notice(
        "S004",
        NoticeType.NO_NOTICE,
        SUV_LOCAL_CASE,
        severity=Severity.MEDIUM,
        state=CaseState.FOLLOW_UP,
        texto=SUV_SILENT_TEXT,
    )
    sel, pl, pb = (news_notice("S004", c) for c in (SEDAN_LOCAL_CASE, PICKUP_LOCAL_CASE, PICKUP_BRAZIL_CASE))
    report = shift_report("T02", "S004", (), ()).model_copy(
        update={
            "novedades": (sel, pl, pb),
            "casos_activos": tuple(
                active_row(c) for c in (SEDAN_LOCAL_CASE, SUV_LOCAL_CASE, PICKUP_LOCAL_CASE)
            ),
        }
    )
    to_mark = (SEDAN_LOCAL_CASE, SUV_LOCAL_CASE, PICKUP_LOCAL_CASE, PICKUP_BRAZIL_CASE)
    return SnapshotNotices((sel, silent, pl, pb), report, to_mark)


def s010_notices() -> SnapshotNotices:
    """E38: closing T05 with an alert and two news."""
    sel, pb = "S008-Sedán-Local", "S007-Pickup-Brasil"
    alert, news_sel, news_pb = alert_notice("S010", sel), news_notice("S010", sel), news_notice("S010", pb)
    decisions = (alert, news_sel, silent_notice("S010", "S008-SUV-Local"), news_pb)
    report = shift_report("T05", "S010").model_copy(update={"novedades": (news_sel, news_pb)})
    return SnapshotNotices(decisions, report, (sel, "S008-SUV-Local", pb))


def empty_close_notices() -> SnapshotNotices:
    """E39: a closing snapshot whose report is empty."""
    return SnapshotNotices((), shift_report("T05", "S010"), ())


class FakeSnapshotWriter:
    """A 'SnapshotWriter' over a plain 'NoticeDraft'; a judgment write only swaps in 'redecided' notices."""

    def __init__(
        self,
        decision: SnapshotDecision,
        max_chars: int = MAX_CHARS,
        *,
        redecided: SnapshotNotices | None = None,
        failure: Exception | None = None,
    ) -> None:
        self._decision = decision
        self._draft = NoticeDraft(decision.notices, max_chars)
        self._redecided = redecided
        self._failure = failure

    def _judged(self) -> JudgmentResult:
        changed: tuple[Notice, ...] = ()
        if self._redecided is not None:
            changed = self._draft.rebase(self._redecided)
            self._decision = replace(self._decision, notices=self._redecided)
        return JudgmentResult((), None, None, changed, self._draft.missing())

    def set_cause(self, case_id: str, cause: Cause, evidence: Evidence) -> JudgmentResult:
        """Swap in the re-decided notices."""
        return self._judged()

    def raise_severity(
        self, categoria: CauseCategory, scope: CauseScope, evidence: Evidence
    ) -> JudgmentResult:
        """Swap in the re-decided notices."""
        return self._judged()

    def lift(self, active_cause_id: str, evidence: Evidence) -> JudgmentResult:
        """Swap in the re-decided notices."""
        return self._judged()

    def write_alert(self, case_id: str, texto: str) -> str:
        """Store an alert text through the draft."""
        return self._draft.write_alert(case_id, texto)

    def write_news(self, texts: Sequence[tuple[str, str]]) -> tuple[str, ...]:
        """Store the report's texts through the draft."""
        return self._draft.write_news(texts)

    def missing(self) -> tuple[str, ...]:
        """Required ids without a text."""
        return self._draft.missing()

    def required(self) -> tuple[str, ...]:
        """Ids of the notices that need a text."""
        return self._draft.required()

    def written(self) -> tuple[str, ...]:
        """Ids written so far."""
        return self._draft.written()

    def final(self) -> SnapshotDecision:
        """The current decision with the draft's texts."""
        return replace(self._decision, notices=self._draft.build())

    def failure(self) -> Exception | None:
        """The failure the test planted, if any."""
        return self._failure


def fake_judgment(
    max_chars: int = MAX_CHARS,
    *,
    redecided: SnapshotNotices | None = None,
    failure: Exception | None = None,
) -> Callable[[SnapshotDecision], FakeSnapshotWriter]:
    """A judgment factory building a 'FakeSnapshotWriter' per decision."""

    def build(decision: SnapshotDecision) -> FakeSnapshotWriter:
        return FakeSnapshotWriter(decision, max_chars, redecided=redecided, failure=failure)

    return build


def draft_frame(draft: NoticeDraft) -> SnapshotFrame:
    """A metric-less frame carrying 'draft' as the notice writer, at the draft's snapshot."""
    snapshot_id = draft.build().decisions[0].snapshot_id
    return SnapshotFrame(
        snapshot_id=snapshot_id, at=datetime(2026, 3, 2, 18, 0), metrics={}, units=(), notices=draft
    )
