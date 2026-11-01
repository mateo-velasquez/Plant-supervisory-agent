# 004 · Notices and shift reports — Spec

- **Status:** Draft
- **Requirements:** FR-21, FR-22, FR-23, FR-24, FR-25, FR-26
- **Stories:** US-04, US-05
- **Week:** W1

## Goal
Decide in code which notices each snapshot produces (immediate alert, shift report or silence), build them in the output contract, and deliver them through a pluggable channel. This closes the threshold-only system: the full series runs without the model.

## Scope
- In: alert rule; novelty rules; shift report (news and active cases); `sin_aviso` record; `motivo` field; deterministic default text; notifier port with console and file adapters; the snapshot pipeline that chains metrics → lifecycle → notices.
- Out: model-written text and cited causes (specs 007 and 008); hooks that check the agent against these rules (spec 010); HTML rendering (spec 014).

## Behavior
- **Alert:** one `alerta_inmediata` in the snapshot where a case becomes `escalado`, at most one per case (FR-21, §4).
- **Report:** one `informe_de_turno` at each closing snapshot (FR-22, §4).
  - **News:** new cases; cases resolved in the shift; cases whose state or severity changed since the last report they appeared in (`abierto` ≡ `en_seguimiento`); cases whose in-shift peak exceeded their closing severity.
  - **Active cases:** every active case with gap, delay, current severity, max severity since the previous report, state and bottleneck (FR-23).
- **Silence:** an unchanged case is never news (FR-24). Each evaluated case without a notice gets a `sin_aviso` record, which is never sent to channels (Q-14).
- **Contract:** every notice has `snapshot_id`, `modelo`, `mercado`, `tipo`, `severidad`, `estado`, `origen`, `motivo`, `causa {categoria, etapa}`, `evidencia [...]` and `texto`; every report has `turno_id`, `novedades` and `casos_activos` (FR-25, Q-13).
- Until spec 008, `origen` is `umbral`, the cause defaults to `no_declarada` with the bottleneck stage, and `texto` comes from a deterministic template.
- **Channels:** a `Notifier` port with console and file adapters (one JSON file per shift plus an alerts file) under `output_dir` (FR-26).

## Worked examples
To be written when the spec moves to Ready. Seeds: US-04 (alert at S020, no second alert) and the six US-05 scenarios (one report per closing snapshot, new and resolved as news, unchanged not news, `abierto` ≡ `en_seguimiento`, peak kept, every active case listed).

## Edge cases and assumptions
- **Q-13:** `motivo` is `gap`, `retraso` or `bitacora`, depending on which severity triggered the escalation.
- **Q-14:** the `sin_aviso` granularity is one record per evaluated case and snapshot.
- A shift with no active cases still produces a report with empty lists.

## Acceptance
- [ ] Every rule above has a passing test.
- [ ] An integration test runs a synthetic mini-series end to end (runner → pipeline → files).
- [ ] `ruff`, `mypy --strict` and `pytest` pass; `docs/STRUCTURE.md` updated.
