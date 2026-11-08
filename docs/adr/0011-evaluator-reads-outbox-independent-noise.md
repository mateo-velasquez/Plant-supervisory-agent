# 0011 · Evaluator reads the registry outbox, re-derives noise independently, and gates by capability

- **Status:** Accepted
- **Date:** 2026-11-07
- **Requirements:** FR-39, FR-40, NFR-07 (Q-33–Q-38)

## Context
The evaluator (spec 005) must tell whether a change improved or broke the system, for the threshold-only baseline now and for model runs from spec 007 on. Every notice decision is already stored in the registry's `notices` table inside the snapshot's transaction (ADR-0010); the channel files are only one projection of it. The noise metric (brief §5) needs no golden data, and the novelty rules it checks live in `cases/novelty.py`: an evaluator that reuses the rule under test cannot detect that rule's error. The golden cases record the full `criterio.md` behaviour, including §5 agent raises and cited causes that the threshold-only system cannot produce yet, so one exit code would fail either the baseline or the model runs.

## Decision
- **Source:** the evaluator scores a pure `RunOutput` (alerts and shift reports in processing order), built by a read-only `read_deliverables(path)` next to the writer in `cases/registry/notices.py`; it shares the deliverable filter with `pending()` and never bootstraps a schema. Channel files are not read.
- **Noise:** re-derived over the output contract only (consecutive reports, `abierto` ≡ `en_seguimiento`); `evaluation/` never imports `cases.novelty`, enforced by an import test.
- **Golden:** one YAML file per day in `evals/golden/`, each declaring the shifts it covers; a case is keyed `{modelo, mercado, abre_en}` and matched through `case_id_for`. Items carry `justification`, optional `depends_on: [Q-xx]` (tracking, still gating) and optional `requires: [agent]`.
- **Gating by capability:** the CLI takes `--capabilities` (default none); items whose `requires` is not met are scored and shown but do not set the exit code.
- **Held out:** a product setting `HELDOUT_OPEN`, distinct from the dev hook's `CLAUDE_ALLOW_HELDOUT`; the held-out set is derived from `turnos.csv` (`HeldOutPolicy` in `domain/calendar.py`).

## Alternatives considered
- **Read the `FileNotifier` files:** they hold only what was delivered, lose processing order across files, and change with each channel.
- **Raw SQL over `notices` inside `evaluation/`:** duplicates the storage format in a second package, and a whole-schema version check would make every stored registry (including paid model runs) unreadable after any unrelated schema bump.
- **Reuse `cases/novelty.py` for noise:** the evaluator would share the bug it should find.
- **Golden of threshold-only behaviour, replaced in spec 008:** throws away hand-verified work and lets model runs fail on correct extra alerts.
- **Make `depends_on` items non-gating:** mixes "depends on an open decision" with "the system cannot do this yet".

## Consequences
- Positive:
  - One source and one golden set serve every mode, from the baseline to the full agent.
  - Noise stays an independent check of the §4 rules.
  - The registry's storage format lives in one place.
- Negative / risks:
  - `cases/registry/notices.py` gains a read path used outside the runner.
  - Golden items must be tagged `requires` correctly; a wrong tag hides a real error.
  - Golden cases built from the smoke run would be circular; they are verified by hand against `criterio.md`.
- Follow-ups:
  - Spec 005 implements the evaluator, the held-out guard and the smoke run.
  - Spec 008 adds run-cause scoring (Q-36) and enables `--capabilities agent`.
  - Specs 006 and 012 reuse `HeldOutPolicy`.
