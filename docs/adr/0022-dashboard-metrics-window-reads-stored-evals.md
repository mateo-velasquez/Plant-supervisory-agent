# 0022 · Dashboard metrics window: stored evaluations, live noise and run reports, read-only

- **Status:** Accepted
- **Date:** 2026-11-20
- **Requirements:** FR-37, FR-39, FR-40, FR-22, FR-38, NFR-06, NFR-07 (spec 015, Q-101–Q-118)

## Context
The live dashboard (ADR-0021) shows cases, notices and agent activity, but not what a run cost per snapshot, how long it took, or how it scored against the golden set. Those numbers already exist on disk: trace lines (tokens, USD, latency), run reports (`OUTPUT_DIR/runs/`, ADR-0018) and evaluator summaries (`eval-*.json`, ADR-0011).

Constraints:
- the dashboard must stay a read-only viewer: no model call, no write, no re-scoring on a poll;
- the evaluator's noise must stay independent of `cases.novelty` (ADR-0011);
- `runner/cli.py` imports `dashboard`, so `dashboard` can never import `runner`;
- `evaluation/summary.py` imports the scorer (`golden`, `scoring`, `causes`, `results`), which the dashboard must not load;
- held-out ids must never be shown while the guard is closed (FR-40).

## Decision
- A third window, **Métricas** (`/metricas`, `/api/metrics`), follows Planta's position over `BroadcastChannel`. Every number derived from the registry and the traces is taken as of that position. The accuracy and run-duration panels are fixed.
- Accuracy is **read, never computed**: the newest `eval-*.json` whose `registry` resolves to the dashboard's registry, shown as stored. The summary gains a `deliverables` count so the page can flag a stale evaluation, and `run_eval` stores the resolved registry path.
- The stored-summary model, `read_summary` and the byte-level writer live in a **leaf module**, `evaluation/summary_file.py`, that imports nothing from the project but `domain`. `evaluation/summary.write_summary` delegates to it, so reader and writer still share one module.
- Live noise reuses `evaluation.noise.count_noise` over the shown deliverables. The dashboard's allowlist is **name-level**: from `evaluation` it may import exactly `output.RunOutput`, `noise.count_noise`, `noise.NoiseScore`, `summary_file.EVAL_NAME`, `summary_file.StoredSummary` and `summary_file.read_summary`. A subprocess probe checks that importing the server loads no scorer module.
- Run durations come from the run reports. The run-report model moves from `runner/summary.py` to `telemetry/run_report.py` with `read_report`; `runner/summary.py` re-exports only what its code and the 012 tests import, and `runner/cli.py` imports the new home. `STAMP_FORMAT`, `ISO_Z_FORMAT` and `TRACE_NAME` get one home in `telemetry/trace.py`.
- Eval summaries and run reports are **written atomically** (a temp name outside the `eval-*.json` / `run-*.json` patterns, then `os.replace`), through a private helper in each owning layer, so the dashboard never reads a half-written file and a report name means a complete report.
- Eval files and run reports that name a refused id are omitted whole and counted. Charts are hand-written SVG through text-node DOM code, with the CSP unchanged.

## Alternatives considered
- **Evaluate inside the dashboard:** it needs the golden set, logbooks and held-out loading on every poll, and makes the viewer a second evaluator.
- **Show any newest eval file:** smoke-run registries live in the same `evals_dir`, so the page could show another run's score.
- **A separate analytics page or static HTML (the old draft):** a second server or build path with its own security contract.
- **`read_summary` inside `evaluation/summary.py`:** importing it loads the scorer into the dashboard.
- **Module-level allowlist (`evaluation.output`, `.noise`, `.summary`):** admits any name added to those modules later.
- **A minimal run-report parser in `dashboard` (option B):** no code moves, but it duplicates field names that can drift silently. Rejected by the user (Q-108).
- **Reuse `notify/atomic.write_atomic`:** `evaluation` and `telemetry` may not import `notify`; moving it to `domain` puts file I/O in the pure layer.
- **A registry fingerprint for staleness:** extra stored state for a rare case (Q-117).
- **A chart library:** a dependency and a CSP or sink-scan exception for a few bar and line charts.

## Consequences
- Positive:
  - Cost, cache share, latency, noise and accuracy can be seen during the replay with no extra command, except running `evals/run_eval.py` for accuracy.
  - Last cumulative USD plus `unplaced_usd` equals Planta's cost by arithmetic (one shared line filter, the same `totals.usd` field).
  - The dashboard never loads the scorer, and no reader sees a partial eval or report file.
- Negative / risks:
  - The dashboard's layer rule widens to six named `evaluation` imports; the import-boundary test locks them.
  - Every field added to `RunReport` later needs a default, or older reports become unreadable.
  - Eval files written before Q-114 store the registry path as given; a relative one matches only from the same working directory.
  - A run that dies without its report reads "En curso o sin informe" forever; threshold-only runs and runs without trace lines are never shown as running (Q-113).
  - A registry rebuilt at the same path with the same deliverable count reads as current (Q-117).
- Follow-ups:
  - Manual review on a real run's `OUTPUT_DIR`, with the user's permission (015 T13).
