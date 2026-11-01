# 011 · Structured output and prompt caching — Plan

## Modules

| File | Responsibility |
|---|---|
| `agents/output.py` | Validate model drafts against `domain/notices.py`; retry with the validation error. |
| `agents/prefix.py` | Build the stable prefix and its hash; place cache breakpoints. |
| `telemetry/usage.py` | Record cache reads and the prefix hash per call. |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
- Nothing that changes per snapshot (timestamps, IDs, deltas) may enter the prefix; it goes after the last breakpoint.

## Test strategy
Unit tests for validation retries and prefix stability (same inputs → same bytes); an integration test of the S034 repeat on the SQLite registry; a real run for cache numbers.

## Risks
Silent cache misses: the prefix hash in the trace makes them visible.
