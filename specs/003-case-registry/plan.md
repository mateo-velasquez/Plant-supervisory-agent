# 003 · Case registry and lifecycle — Plan

## Modules

| File | Responsibility |
|---|---|
| `domain/cases.py` | `CaseState` (Spanish values, ADR-0005), `Case`, `CaseHistoryRow`. |
| `cases/lifecycle.py` | `apply(metrics, active_case, raise_in_force, thresholds) -> Transition` (State pattern). |
| `cases/registry.py` | `Registry` protocol, `InMemoryRegistry` and `SqliteRegistry`. |
| `cases/schema.sql` | Tables `cases`, `case_history`, `processed_snapshots` (with hash), `released_units`. |
| `config.py` | Registry file path derived from `output_dir`. |

## Types and interfaces
To be fixed when the spec moves to Ready. `SqliteRegistry` also implements `ProcessedStore` from spec 002.

## Design notes
- State pattern per `docs/STRUCTURE.md`; the lifecycle is pure, and the registry does the I/O.
- One `unit_of_work(snapshot_id)` context manager wraps every write for a snapshot plus `mark_processed`.
- `sqlite3` from the standard library (ADR-0003); tests use `:memory:`.

## Test strategy
Unit tests for every transition with synthetic `CombinationMetrics`; repository contract tests run against both implementations; a rollback test for a failure in the middle of a snapshot.

## Risks
Effective severity computed in two places would drift: it lives only in `lifecycle.py`.
