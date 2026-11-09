"""Notice draft: tracks the agent's texts for the required notices and rebuilds them (R1, R8-R10)."""

from collections.abc import Sequence

from plant_monitor.cases.notice_builder import SnapshotNotices
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.domain.notices import Notice, NoticeType, ShiftReport


class NoticeNotDecided(RejectedRequest):
    """The alert the model wants to write is not decided at this snapshot."""

    def __init__(self, case_id: str, snapshot_id: str) -> None:
        super().__init__(f"no alerta_inmediata is decided for {case_id} at {snapshot_id}")


class ReportNotDecided(RejectedRequest):
    """No shift report is decided at this snapshot."""

    def __init__(self, snapshot_id: str) -> None:
        super().__init__(f"no shift report is decided at {snapshot_id}")


class TextAlreadyWritten(RejectedRequest):
    """The texts were already written; a write happens once."""

    @classmethod
    def alert(cls, case_id: str) -> TextAlreadyWritten:
        """Refusal for a second alert text."""
        return cls(f"alerta_inmediata texto for {case_id} is already written")

    @classmethod
    def report(cls, turno_id: str) -> TextAlreadyWritten:
        """Refusal for a second report write."""
        return cls(f"shift report texts for {turno_id} are already written")


class NotNews(RejectedRequest):
    """A 'case_id' that is not a news item of the report."""

    def __init__(self, case_id: str, turno_id: str) -> None:
        super().__init__(f"{case_id} is not a news item of {turno_id}")


class DuplicateNews(RejectedRequest):
    """A 'case_id' listed twice in 'textos'."""

    def __init__(self, case_id: str) -> None:
        super().__init__(f"{case_id} appears twice in textos")


class MissingNews(RejectedRequest):
    """News items without a text in 'textos'."""

    def __init__(self, case_ids: Sequence[str]) -> None:
        super().__init__(f"missing texto for {', '.join(case_ids)}")


class InvalidText(RejectedRequest):
    """An empty or too long text."""

    @classmethod
    def empty(cls, case_id: str) -> InvalidText:
        """Refusal for a blank text."""
        return cls(f"texto for {case_id} is empty")

    @classmethod
    def too_long(cls, case_id: str, length: int, maximum: int) -> InvalidText:
        """Refusal for a text over the maximum."""
        return cls(f"texto for {case_id} is {length} characters, over the maximum of {maximum}")


def _with_text(notice: Notice, texto: str) -> Notice:
    return Notice.model_validate({**notice.model_dump(), "texto": texto})


def _identity(notice: Notice) -> dict[str, object]:
    return notice.model_dump(mode="json", exclude={"texto"})


def _news_identities(news: Sequence[Notice]) -> list[tuple[str, dict[str, object]]]:
    return [(n.case_id, _identity(n)) for n in news]


class NoticeDraft:
    """The snapshot's notices with template texts, plus the texts the agent wrote."""

    def __init__(self, notices: SnapshotNotices, max_chars: int) -> None:
        self._max_chars = max_chars
        self._texts: dict[str, str] = {}
        self._load(notices)

    def _load(self, notices: SnapshotNotices) -> None:
        self._notices = notices
        self._alerts = {n.case_id: n for n in notices.decisions if n.tipo is NoticeType.ALERT}
        self._news = notices.report.novedades if notices.report is not None else ()
        self._required = frozenset(
            [n.notice_id for n in self._alerts.values()] + [n.notice_id for n in self._news]
        )

    def rebase(self, notices: SnapshotNotices) -> tuple[Notice, ...]:
        """Swap in re-decided notices, keeping texts of unchanged ones (R13); return the changed ones."""
        old = {n.notice_id: _identity(n) for n in self._notices.decisions}
        old_news = _news_identities(self._news)
        self._load(notices)
        new = {n.notice_id: _identity(n) for n in notices.decisions}
        news_ids = {n.notice_id for n in self._news}
        news_kept = old_news == _news_identities(self._news)

        def kept(nid: str) -> bool:
            return news_kept if nid in news_ids else old.get(nid) == new.get(nid)

        self._texts = {nid: text for nid, text in self._texts.items() if nid in self._required and kept(nid)}
        return tuple(
            n
            for n in notices.decisions
            if n.notice_id in self._required and old.get(n.notice_id) != new[n.notice_id]
        )

    @property
    def _snapshot_id(self) -> str:
        if self._notices.report is not None:
            return self._notices.report.snapshot_id
        return self._notices.decisions[0].snapshot_id if self._notices.decisions else ""

    def required(self) -> tuple[str, ...]:
        """Alert ids, then news ids in report order."""
        return (*(n.notice_id for n in self._alerts.values()), *(n.notice_id for n in self._news))

    def missing(self) -> tuple[str, ...]:
        """Required ids not written yet, in decision order."""
        return tuple(
            n.notice_id
            for n in self._notices.decisions
            if n.notice_id in self._required and n.notice_id not in self._texts
        )

    def written(self) -> tuple[str, ...]:
        """Ids written so far, in decision order."""
        return tuple(n.notice_id for n in self._notices.decisions if n.notice_id in self._texts)

    def _checked(self, case_id: str, texto: str) -> str:
        """The stripped text, or the R8 text refusals (empty, then too long)."""
        text = texto.strip()
        if not text:
            raise InvalidText.empty(case_id)
        if len(text) > self._max_chars:
            raise InvalidText.too_long(case_id, len(text), self._max_chars)
        return text

    def write_alert(self, case_id: str, texto: str) -> str:
        """Store the alert text of 'case_id' and return its notice id (R8)."""
        alert = self._alerts.get(case_id)
        if alert is None:
            raise NoticeNotDecided(case_id, self._snapshot_id)
        if alert.notice_id in self._texts:
            raise TextAlreadyWritten.alert(case_id)
        self._texts[alert.notice_id] = self._checked(case_id, texto)
        return alert.notice_id

    def write_news(self, texts: Sequence[tuple[str, str]]) -> tuple[str, ...]:
        """Store every news text of the report atomically and return their ids (R9)."""
        report = self._notices.report
        if report is None:
            raise ReportNotDecided(self._snapshot_id)
        if any(n.notice_id in self._texts for n in self._news):
            raise TextAlreadyWritten.report(report.turno_id)
        by_case = {n.case_id: n for n in self._news}
        seen: set[str] = set()
        for case_id, _ in texts:
            if case_id in seen:
                raise DuplicateNews(case_id)
            if case_id not in by_case:
                raise NotNews(case_id, report.turno_id)
            seen.add(case_id)
        absent = [n.case_id for n in self._news if n.case_id not in seen]
        if absent:
            raise MissingNews(absent)
        checked = {case_id: self._checked(case_id, texto) for case_id, texto in texts}
        for case_id, text in checked.items():
            self._texts[by_case[case_id].notice_id] = text
        return tuple(n.notice_id for n in self._news)

    def build(self) -> SnapshotNotices:
        """Rebuild the written notices through the validators; 'casos_activos' and 'to_mark' unchanged."""
        if not self._texts:
            return self._notices

        def rebuilt(notice: Notice) -> Notice:
            text = self._texts.get(notice.notice_id)
            return notice if text is None else _with_text(notice, text)

        report = self._notices.report
        new_report = (
            None
            if report is None
            else ShiftReport(
                turno_id=report.turno_id,
                snapshot_id=report.snapshot_id,
                novedades=tuple(rebuilt(n) for n in report.novedades),
                casos_activos=report.casos_activos,
            )
        )
        return SnapshotNotices(
            tuple(rebuilt(n) for n in self._notices.decisions), new_report, self._notices.to_mark
        )
