# 0004 · Real data not versioned; synthetic fixtures for tests

- **Status:** Accepted
- **Date:** 2026-10-18
- **Requirements:** NFR-07, FR-40

## Context
The dataset is course material. Versioning it adds weight and exposure without value, and CI must not depend on it. Days 8–10 must also stay out of tuning until W5.

## Decision
`data/` is git-ignored except its README, and its location is configurable via `DATA_DIR`. Tests and CI use a small **synthetic** dataset in `tests/fixtures/`, built by hand to exercise each rule. Golden eval cases (`evals/golden/`) cover days 1–7 only.

## Alternatives considered
- **Version the data:** simplest CI, but bad practice for third-party material, and it makes held-out days easy to leak into tuning.
- **Download in CI from a private location:** extra secrets and setup for no real gain at this stage.

## Consequences
- Positive: CI is fast and offline, and fixtures document the rules with tiny, readable examples.
- Negative: fixtures must be kept faithful to the real schema; the schema validation in ingestion (FR-03) protects this.
