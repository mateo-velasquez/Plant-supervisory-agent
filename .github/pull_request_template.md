## Summary
<!-- What this PR does and why, in one or two sentences. -->

## Changes
-

## Traceability
- **Spec:** <!-- specs/NNN-feature, or n/a -->
- **Requirements:** <!-- FR-xx, NFR-xx -->
- **Stories:** <!-- US-xx -->
- **ADR:** <!-- docs/adr/NNNN, if a decision was made -->

## How to test
```powershell
uv sync
uv run ruff check . ; uv run ruff format --check . ; uv run mypy src tests ; uv run pytest --cov
```

## Checklist
- [ ] Tests added or updated for every rule touched
- [ ] Docs updated (`STRUCTURE.md`, spec status, ADR if needed)
- [ ] No data from `data/` and no held-out days (8–10) used for tuning
- [ ] No secrets, `.env` or real data committed
