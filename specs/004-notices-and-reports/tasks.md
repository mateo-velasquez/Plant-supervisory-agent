# 004 · Notices and shift reports — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · `domain/notices.py` models with FR-25 fields plus `motivo`; validation tests (enum values, `origen` only `umbral` or `agente`).
- [ ] T2 · Alert test (US-04): a case that becomes `escalado` at S020 yields one `alerta_inmediata` with `snapshot_id` S020 and the right `motivo` → `cases/novelty.py`.
- [ ] T3 · Test: an already escalated case never alerts again.
- [ ] T4 · News test: new cases and cases resolved in the shift are news.
- [ ] T5 · News test: unchanged state and severity are not news; `abierto` → `en_seguimiento` with the same severity is not news.
- [ ] T6 · News test: an in-shift peak above the closing severity is news, with current and max severity.
- [ ] T7 · Active-cases test: every active case appears with gap, delay, current and max severity, state and bottleneck.
- [ ] T8 · Test: exactly one report per closing snapshot, none at mid snapshots; the registry's last reported state and severity are updated after it.
- [ ] T9 · `sin_aviso` test (Q-14): one record per evaluated case without a notice; never sent to notifiers.
- [ ] T10 · Default text and cause test: threshold-only notices use `origen=umbral`, `no_declarada` with the bottleneck stage, and template text.
- [ ] T11 · `Notifier` port plus console and file adapters (JSON per shift, alerts file) with `tmp_path` tests.
- [ ] T12 · `ThresholdPipeline` test on one snapshot with two combinations: metrics → lifecycle → notices → registry → notifiers.
- [ ] T13 · Integration test: runner (002) + SQLite registry (003) + pipeline over a 2-shift synthetic series produce the expected alerts and reports.
- [ ] T14 · Update `docs/STRUCTURE.md`, the shift-close diagram if needed, and set status to Implemented.
