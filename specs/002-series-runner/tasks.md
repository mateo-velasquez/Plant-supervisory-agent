# 002 · Series runner — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · `Arrival` and `ShiftPosition` in `domain/` with validation tests.
- [ ] T2 · Synthetic `llegadas.csv` fixture (BOM, one repeated snapshot) and failing tests: sorted by `orden`, BOM stripped, malformed row names file, row and field → `ingestion/arrivals.py`.
- [ ] T3 · `ShiftIndex` tests: S001 is the mid snapshot of T01, S002 its closing one; an unknown snapshot raises → `ingestion/shift_index.py`.
- [ ] T4 · Test that a snapshot whose `turno` disagrees with `turnos.csv` raises a data error → check in `ShiftIndex`.
- [ ] T5 · `content_hash` test (same bytes, same hash; one byte changed, different hash) → `ingestion/hashing.py`.
- [ ] T6 · `ProcessedStore` and `SnapshotPipeline` protocols plus the in-memory store, with tests for `get_hash` and `mark_processed`.
- [ ] T7 · Runner test: S001, S002, S003 reach the pipeline in that order with their shift and position → `runner/series.py`.
- [ ] T8 · Runner test: a repeated identical snapshot never reaches the pipeline and logs `"S034 skipped: already processed"`.
- [ ] T9 · Runner test (Q-10): a repeat with a different hash is not reprocessed and appears as an anomaly in `RunSummary`.
- [ ] T10 · Runner test: the pipeline fails at the third snapshot, it stays unprocessed, and a second run resumes there without repeating the first two.
- [ ] T11 · Runner test: a listed snapshot missing on disk fails naming the file.
- [ ] T12 · `RunSummary` (processed, skipped, anomalies) with a test.
- [ ] T13 · Import-boundary test: `ingestion` and `runner/series.py` do not import `anthropic` or `mcp`.
- [ ] T14 · Update `docs/STRUCTURE.md` and set this spec's status to Implemented.
