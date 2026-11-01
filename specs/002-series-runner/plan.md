# 002 · Series runner — Plan

## Modules

| File | Responsibility |
|---|---|
| `domain/models.py` | Add `Arrival` and `ShiftPosition` (`mid`, `closing`). |
| `ingestion/arrivals.py` | `load_arrivals(path) -> list[Arrival]` (`utf-8-sig`, validated, sorted by `orden`). |
| `ingestion/shift_index.py` | `ShiftIndex.locate(snapshot_id) -> (Shift, ShiftPosition)` built from `turnos.csv`. |
| `ingestion/hashing.py` | `content_hash(path) -> str` (SHA-256 of the file bytes). |
| `runner/ports.py` | `ProcessedStore` and `SnapshotPipeline` protocols. |
| `runner/memory_store.py` | In-memory `ProcessedStore` for tests. |
| `runner/series.py` | `run_series(arrivals, store, pipeline, ctx) -> RunSummary`. |

## Types and interfaces
To be fixed when the spec moves to Ready. Sketch: `ProcessedStore.get_hash(snapshot_id) -> str | None` and `mark_processed(snapshot_id, hash)`; `SnapshotPipeline.process(snapshot, shift, position) -> None`.

## Design notes
- Pipeline pattern: the runner only orders, deduplicates and delegates.
- `ProcessedStore` is a port so spec 003 can plug SQLite in, where marking processed shares the transaction with the pipeline's writes (ADR-0003).

## Test strategy
Unit tests with synthetic `llegadas.csv` and `turnos.csv` (written with BOM), a fake pipeline that records calls, and `caplog` for skip messages.

## Risks
Marking processed outside the pipeline's transaction would break resume; the SQLite version in spec 003 must keep both in one transaction.
