# 004 · Notices and shift reports — Plan

## Modules

| File | Responsibility |
|---|---|
| `domain/notices.py` | `NoticeType`, `Origin`, `Reason` (`motivo`), `Notice`, `ActiveCaseRow`, `ShiftReport`, `SilentDecision`. |
| `cases/novelty.py` | `alerts_for(transitions)`, `expected_news(cases, last_reported)`, `active_rows(cases, metrics)`. |
| `notify/port.py` | `Notifier` protocol. |
| `notify/console.py`, `notify/file.py` | Console and JSON-per-shift adapters. |
| `notify/templates.py` | Deterministic default `texto`. |
| `runner/pipeline.py` | `ThresholdPipeline`: metrics → lifecycle → notices → registry → notifiers (implements `SnapshotPipeline`). |

## Types and interfaces
To be fixed when the spec moves to Ready. `Notice` and `ShiftReport` are frozen pydantic models; their JSON is the output contract that spec 011 validates.

## Design notes
- Ports and Adapters for channels (`docs/STRUCTURE.md`).
- Novelty rules are pure functions over registry data, so spec 010's hooks can reuse them as the expected answer.

## Test strategy
Unit tests per rule; adapter tests with `tmp_path`; one integration test over a 2-shift synthetic series.

## Risks
Novelty logic duplicated between code and hooks would drift: hooks must call `cases/novelty.py`, never reimplement it.
