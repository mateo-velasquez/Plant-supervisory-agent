# 009 · Multi-agent with a single writer — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `domain/numbers.py` | New | `DECIMALS` (moved from `mcp_server/views.py`), `round_display`, `round_optional`. |
| `domain/proposals.py` | New | `ProposalKind`, `CauseState`, the three proposal models, `Proposal`, `InvestigatorOutput`, `ValidatedProposal`, `proposal_id_for`. |
| `domain/perspectives.py` | New | `GapAtReport`, `GapPerspective`, `ShipmentPerspective`, `BottleneckPerspective`, `CasePerspective`. |
| `cases/reviews.py` | New | Pure review rules: `ReviewMark`, `LogbookReview`, `pending_logbooks`, `review_succeeded`, `next_review`. |
| `cases/registry/schema.py`, `sqlite.py` | Changes | `MIGRATION_V3_TO_V4_BODY`, `STEPS`, `migration_from`, `SCHEMA_VERSION` 4; `registry.reviews`. |
| `cases/registry/reviews_repo.py` | New | `ReviewStore` protocol, `SqliteReviewRepository`. |
| `cases/perspectives.py` | New | `gap_perspective`. |
| `metrics/shipment.py` | New | `shipment_perspective`. |
| `mcp_server/views.py` | Changes | Imports `DECIMALS` and the rounding helpers from `domain/numbers.py`; behavior unchanged. |
| `ingestion/logbooks.py`, `logbooks/errors.py`, `logbooks/store.py` | Changes | `LogbookFileMissing`; `LogbookMissing`; `LogbookStore.get` maps it, `missing()`. |
| `agents/loop.py` | Changes | `EndReview`, `MissingTexts`, `LoopOutcome.INVALID_OUTPUT`, one end-of-turn path, `run(..., review=None)`. |
| `agents/control.py` | New | `CitationCheck`, `TaskCase`, `InvestigatorTask`, `ControlResult`, `check_output`. |
| `agents/investigator.py` | New | `render_task`, `ReviewLog`, `ProposalReview`, `NothingRequired`, `TASK_INSTRUCTION`, `CORRECTION_HEADER`. |
| `agents/factory.py`, `prompts/investigator.md`, `prompts/coordinator.md` | Changes | `INVESTIGATOR_TOOLS`, new `COORDINATOR_TOOLS`, `load_prompt(name)`, `build_investigator`; prompt v1 and v3. |
| `agents/brief.py` | Changes | `cause_item` (public), `render_brief` with perspectives and proposals, `render_proposals`. |
| `mcp_server/context.py`, `write_tools.py`, `server.py` | Changes | `ProposalBook`, frame `proposals`; `apply_proposal`; `WRITE_TOOLS` gains it. |
| `runner/pipeline.py` | Changes | `SnapshotDecision.cited`. |
| `runner/bridge.py` | New | `run_in_frame` (frame enter, `anyio.run`, single-leaf unwrap), moved out of `agent_pipeline.py`. |
| `runner/review_step.py` | New | `ReviewPlan`, `ReviewOutcome`, `LogbookReviewStep` protocol, `InvestigatorStep`. |
| `runner/perspectives.py` | New | `case_perspectives`. |
| `runner/coordinator_step.py` | New | `CoordinatorOutcome`, `CoordinatorStep`. |
| `runner/agent_pipeline.py` | Changes | Sequences the steps, picks the R9 reason, stages the line; `build_agent_pipeline` with two servers. |
| `telemetry/trace.py` | Changes | `DecisionReason`, `_costed`, `InvestigatorRecord`, `TraceInvestigator`, new line fields, `AgentRunTotals`, `RunTotals.by_agent`. |
| `config.py`, `.env.example` | Adds | R15 settings. |
| `evals/agent_days_1_7.py` | Changes | Prints `by_agent`. |
| `tests/incident_builders.py` | Adds | `copy_incident_logbooks(directory, omit=())` (E14, E22, E25). No new versioned fixture file. |

## Types and interfaces

### Proposal types
`domain/proposals.py`, frozen pydantic, `extra="forbid"`:
- `ProposalKind(StrEnum)`: `SET_CAUSE = "set_cause"`, `RAISE = "raise"`, `LIFT = "lift"`. `CauseState(StrEnum)`: `ACTIVE_NO_DATE = "activa_sin_fecha"`, `DATED = "con_fecha"`, `RESOLVED = "resuelta"`.
- `SetCauseProposal(tipo: Literal["set_cause"], case_id: str, categoria: CauseCategory, etapa: Stage, bitacora: str, fragmento: str, estado_causa: CauseState)`.
- `RaiseProposal(tipo: Literal["raise"], categoria, etapa, modelo: Model, mercado: Market | None = None, bitacora, fragmento, estado_causa)`, property `scope -> CauseScope`.
- `LiftProposal(tipo: Literal["lift"], causa_activa: str, bitacora, fragmento, estado_causa)`.
- `Proposal = Annotated[SetCauseProposal | RaiseProposal | LiftProposal, Field(discriminator="tipo")]`; `InvestigatorOutput(propuestas: tuple[Proposal, ...])`.
- `ValidatedProposal(id: str, proposal: Proposal)` with `item() -> dict[str, JsonValue]` (`{"id", …}`, the brief and trace shape). `def proposal_id_for(snapshot_id: str, n: int) -> str` → `S010-p1`.
- `etapa` accepts production stages only (a validator). `no_declarada` passes the schema; control refuses it with its own message (R5 4a).

### Loop end-of-turn path
`agents/loop.py`:
- `class EndReview(Protocol)`: `review(self, text: str) -> str | None`; `exhausted: LoopOutcome` (read-only property).
- `class MissingTexts(progress: TextProgress)`: `review` returns `None` when `progress.missing()` is empty, else `render_reminder(missing)`; `exhausted = MISSING_TEXTS`.
- `Coordinator.run(snapshot_id, brief, progress, log, review: EndReview | None = None)`; `None` means `MissingTexts(progress)`, so 007/008 call sites are unchanged.
- At `end_turn`, the only branch: `note = review.review(text)` (the reply's text blocks joined by `\n`); `None` → `DONE`; a note when none was given → append it as a user turn; a second note → `review.exhausted`. After `tool_use`, `progress` alone decides the early stop (008 rule). One path is the seam for 010's on-stop hooks and 011's validation.
- `LoopOutcome.INVALID_OUTPUT = "fallback:invalid_output"`.

### Control
`agents/control.py`:
- `class CitationCheck(Protocol)`: `verify_citation(turno_id: str, fragment: str, snapshot_id: str) -> None`, raising `RejectedRequest`. `LogbookStore` satisfies it.
- `TaskCase(case_id, modelo: Model, mercado: Market, estado: CaseState, etapa: Stage | None)`; `InvestigatorTask(snapshot_id, turno_id, position: ShiftPosition, logbooks: tuple[str, ...], cases: tuple[TaskCase, ...], active_causes: tuple[tuple[ActiveCause, tuple[str, ...]], ...])`.
- `ControlResult(accepted: tuple[ValidatedProposal, ...] | None, errors: tuple[str, ...])`: `accepted` is `None` iff `errors`.
- `def check_output(text: str, task: InvestigatorTask, citations: CitationCheck, max_chars: int) -> ControlResult`: R5 order; fence strip is one leading ```` ```json ````/```` ``` ```` line and one trailing ```` ``` ```` line; `json.loads`, then `InvestigatorOutput.model_validate`; `fragmento` is passed stripped to the check.

### Investigator invocation
`agents/investigator.py`:
- `TASK_INSTRUCTION`, `CORRECTION_HEADER` (R6 text); `def render_task(task: InvestigatorTask) -> str` (R2 JSON, `brief.cause_item`).
- `class NothingRequired`: `required()` and `missing()` return `()`.
- `ReviewLog` (mutable dataclass, created by the pipeline per snapshot): `rejections: list[tuple[str, ...]]`, `accepted: tuple[ValidatedProposal, ...] | None = None`.
- `class ProposalReview(task, citations, max_chars, log: ReviewLog)`: an `EndReview`; `review(text)` runs `check_output`, appends errors to `log.rejections` or sets `log.accepted`, returns `CORRECTION_HEADER` + `- <error>` lines or `None`; `exhausted = INVALID_OUTPUT`.
- `agents/factory.py`: `INVESTIGATOR_TOOLS`, `COORDINATOR_TOOLS` as literals (R12 order); `load_prompt(name: Literal["coordinator", "investigator"] = "coordinator")`; `build_investigator(settings, model, tools) -> Coordinator` (`max_turns = investigator_max_turns`).

### Review step
`runner/review_step.py` (types `LogbookStore` directly):
- `ReviewPlan(present: tuple[str, ...], missing: tuple[str, ...])`, property `pending`.
- `ReviewOutcome(plan: ReviewPlan, ran: bool, outcome: LoopOutcome | None, accepted: tuple[ValidatedProposal, ...])`; `valid` = `ran and outcome is DONE and accepted log set`.
- `class LogbookReviewStep(Protocol)`: `plan(decision) -> ReviewPlan`; `run(plan, decision, log: LoopLog, review_log: ReviewLog) -> ReviewOutcome`; `record(outcome: ReviewOutcome, coordinator: LoopOutcome | None, snapshot_id: str) -> Mapping[str, ReviewMark]`. The 007/008 pipeline tests pass a fake with an empty plan.
- `InvestigatorStep(investigator: Coordinator, frames: FrameHolder, logbooks: LogbookStore, reviews: ReviewStore, max_attempts: int, max_chars: int)`:
  - `plan`: `pending_logbooks(available ids, reviews.get(ids))`, then `logbooks.missing`.
  - `run`: when `present`, the task (cases = `decision.candidates` not in `decision.cited`, active causes = `decision.in_force`), frame `SnapshotFrame(sid, at, metrics, units)` with no writer and no book, `run_in_frame(..., investigator.run, sid, render_task(task), NothingRequired(), log, ProposalReview(..., review_log))`. Writes nothing.
  - `record(outcome, coordinator, snapshot_id, applied=())` (`applied` = the book's applied proposal ids): `success = review_succeeded(outcome.valid, <accepted ids not in applied>, None if coordinator is None else coordinator is DONE)` (true iff `valid` and (`unapplied == 0` or `coordinator_done is True`), Q-53) for present logbooks, `False` for missing ones; `next_review` per logbook; `reviews.save(...)`; returns the marks. Called by the pipeline after the coordinator step.

### Coordinator step
`runner/coordinator_step.py`:
- `CoordinatorOutcome(outcome: LoopOutcome, applied: tuple[str, ...], declined: tuple[str, ...])`.
- `CoordinatorStep(coordinator: Coordinator, frames: FrameHolder, perspectives: Callable[[SnapshotDecision, Sequence[str]], tuple[CasePerspective, ...]])`; `run(decision, writer: SnapshotWriter, accepted: Sequence[ValidatedProposal], log: LoopLog) -> CoordinatorOutcome`: `ProposalBook(accepted)`, perspectives for `writer.required()`, `render_brief`, `SnapshotFrame.with_writer(..., proposals=book)`, `run_in_frame(..., coordinator.run, sid, brief, writer, log)` (default `MissingTexts`).

### `apply_proposal` and the frame
- `mcp_server/context.py`: `class ProposalBook(proposals: Sequence[ValidatedProposal])`: `get(proposal_id, snapshot_id) -> Proposal` (raises `UnknownProposal`, `ProposalApplied`); `mark_applied(proposal_id)`; `applied()`, `declined()` in book order. Refusals are `RejectedRequest` with the R11 texts.
- `SnapshotFrame` gains `proposals: ProposalBook | None = None`; `with_writer(..., writer, proposals: ProposalBook | None = None)`.
- `write_tools.apply_proposal(ctx, frames, propuesta: str) -> str`: R11 order; `NoProposalBook` for check 1; dispatch with `match proposal:` over the three classes and `assert_never` on the rest, to `frame.causes.set_cause`, `frame.raises.raise_severity`, `frame.raises.lift`; `mark_applied` only after the writer returns. No new writer protocol: `CauseWriter`/`RaiseWriter` (implemented by `SnapshotJudgment`) are the write path, so 008's failure guard covers it.
- `server.WRITE_TOOLS = ("set_cause", "raise_severity", "lift_severity_raise", "apply_proposal", "emit_alert", "emit_shift_report")`; wrapper `async def apply_proposal(propuesta: str) -> str`. `build_server` is otherwise unchanged; the 008 judgment tools stay registrable and tested (X9).

### Perspectives
- `domain/numbers.py`: `DECIMALS: Final = 1`, `round_display(value: float) -> float`, `round_optional(value: float | None) -> float | None`. `mcp_server/views.py` imports them (006 tests unchanged).
- `domain/perspectives.py` (frozen, Spanish field names): `GapAtReport(snapshot_id, unidades: float, pct_plan_diario: float | None)`; `GapPerspective(unidades, pct_plan_diario, en_ultimo_informe: GapAtReport | None)`; `ShipmentPerspective(unidades_demoradas: int, retraso_dias: float | None, embarque_asignado: str | None, embarque_alcanzable: str | None)`; `BottleneckPerspective(etapa: Stage | None)`; `CasePerspective(case_id, gap, embarque, cuello)`.
- `cases/perspectives.py`: `def gap_perspective(case: Case, now: CombinationMetrics, history: Sequence[CaseHistoryRow]) -> GapPerspective`, rounded; a set `last_reported_at` with no row raises `ValueError`. Spec 016 adds `tendencia` to `GapPerspective` (and the inputs it needs); the 009 contract is the brief shape, not this signature.
- `metrics/shipment.py`: `def shipment_perspective(units: Sequence[Unit], combination: Combination, at: datetime, metrics: CombinationMetrics, plant: PlantContext) -> ShipmentPerspective`, rounded, using `is_delayed`, `unit_delay_days`, `projected_yard_arrival`, `reachable_shipment` (R10 worst-unit order).
- `runner/perspectives.py`: `def case_perspectives(decision: SnapshotDecision, required: Sequence[str], cases: CaseReader, plant: PlantContext) -> tuple[CasePerspective, ...]`, reusing `mcp_server.context.CaseReader` (`get_case`, `history`); `runner` may import `mcp_server.context` (as `runner/judgment.py` does), so no new protocol.

### Brief v3
`render_brief(snapshot_id, turno_id, position, alerts, news, active_causes=(), perspectives: Sequence[CasePerspective] = (), proposals: Sequence[ValidatedProposal] = ())`: instruction line, JSON line (`perspectivas` after `causas_activas`), then `render_proposals(snapshot_id, proposals)` when not empty; it escapes `<(/?propuestas)` case-insensitively in each JSON line.

### Registry v4
- `logbook_reviews(turno_id TEXT PRIMARY KEY, attempts INTEGER NOT NULL CHECK (attempts >= 1), last_attempt_at TEXT NOT NULL, reviewed_at TEXT, given_up_at TEXT, CHECK (reviewed_at IS NULL OR given_up_at IS NULL))`.
- `schema.py`: `SCHEMA_V2_BODY`, `MIGRATION_V2_TO_V3_BODY` (frozen), `MIGRATION_V3_TO_V4_BODY`; `STEPS: Final[Mapping[int, str]] = {2: MIGRATION_V2_TO_V3_BODY, 3: MIGRATION_V3_TO_V4_BODY}`; `def migration_from(version: int) -> str` = the steps from `version` up, then `PRAGMA user_version = 4` (`KeyError`-free: only called for keys of `STEPS`); `SCHEMA` = `BEGIN;` v2 body + `migration_from(2)` + `COMMIT;`. The 008 `MIGRATION_V2_TO_V3` constant is replaced, so no step claims a version it does not build.
- `sqlite.py`: 0 → `SCHEMA`; a key of `STEPS` → `migration_from(v)` inside one `BEGIN IMMEDIATE` … `COMMIT`, statements one by one, `ROLLBACK` + close + re-raise on error; 4 → open; else `ValueError`.
- `cases/reviews.py`: `ReviewMark(StrEnum)`: `REVIEWED = "revisada"`, `RETRY = "reintento"`, `GIVEN_UP = "sin_revisar"`. `LogbookReview(turno_id, attempts, last_attempt_at, reviewed_at: str | None, given_up_at: str | None)`, property `settled`. `pending_logbooks(available: Sequence[str], reviews: Mapping[str, LogbookReview]) -> tuple[str, ...]`; `review_succeeded(valid: bool, proposals: int, coordinator_done: bool | None) -> bool` (Q-53); `next_review(current: LogbookReview | None, turno_id, snapshot_id, succeeded: bool, max_attempts: int) -> tuple[LogbookReview, ReviewMark]`.
- `ReviewStore(Protocol)`: `get(turno_ids: Collection[str]) -> dict[str, LogbookReview]`; `save(review: LogbookReview) -> None` (upsert through `session.require_open`; `last_attempt_at` must be the open snapshot). Re-exported from `cases.registry`.

### Missing logbooks
- `ingestion/logbooks.py`: `class LogbookFileMissing(DataLoadError)`, raised for a missing `<turno_id>.txt` (same message).
- `logbooks/errors.py`: `LogbookMissing(RejectedRequest)` (`logbook <T> is missing`). `LogbookStore.get` turns the loader's `LogbookFileMissing` into it; `missing(turno_ids, snapshot_id) -> tuple[str, ...]` collects the ids whose `get` raises it.

### Trace
- `DecisionReason = Literal["text_needed", "proposals", "investigator_only", "no_text_needed", "closing_review"]` (`closing_review` read-only).
- `_costed(calls: Sequence[ModelCallRecord], card: PriceCard) -> tuple[list[TraceModelCall], TraceTotals]`, shared by the line and the investigator entry.
- `InvestigatorRecord` (dataclass): `outcome: str`, `logbooks`, `missing`, `marks: Mapping[str, str]`, `proposals: Sequence[Mapping[str, JsonValue]]`, `control_errors: Sequence[Sequence[str]]`, `model_calls`, `tool_calls`, `thinking`. `TraceInvestigator` (pydantic): the same, costed, with `totals`.
- `TraceLine` gains `agents_run: list[Literal["investigator", "coordinator"]] | None = None` (`None` on old lines; read through a property `ran` that derives R14's fallback), `investigator: TraceInvestigator | None = None`, `proposals_applied: list[str] = []`, `proposals_declined: list[str] = []`. Its docstring says `totals` sums every agent and may differ from the top-level `model_calls`.
- `build_line(..., agents_run: Sequence[str] = (), investigator: InvestigatorRecord | None = None, proposals_applied=(), proposals_declined=())`.
- `AgentRunTotals(runs, model_calls, input_tokens, output_tokens, usd)`; `RunTotals.by_agent: dict[Literal["investigator", "coordinator"], AgentRunTotals]`; `RunTotals.model_calls` counts both agents.

### `AgentPipeline`
- `AgentPipeline(steps, unit, frames, trace, prices, judgment, review: LogbookReviewStep, coordinator: CoordinatorStep)`; it holds no loop or brief logic.
- `process`: `decide` → writer → `review.plan` → provisional reason (R9) → unit check if a model may be called → `review.run` when `plan.present` (agents_run += investigator) → `proposals` upgrade → `coordinator.run` when due (agents_run += coordinator) → failure check → `review.record` when `plan.pending` → `finish` → stage. On an exception: `write_now` with the `LoopLog`s and `ReviewLog` gathered so far (top outcome `skipped` when the coordinator never started), then re-raise.
- `build_agent_pipeline` builds one `LogbookStore`, two servers (`INVESTIGATOR_TOOLS`, `COORDINATOR_TOOLS`) over one `FrameHolder`, both loops on the same `model`, `InvestigatorStep(..., registry.reviews, ...)`, `CoordinatorStep` with `case_perspectives` over `registry.cases` and `ctx`.
- `SnapshotDecision.cited: frozenset[str] = frozenset()`, set in `_notices_for` from the `cited` map it already builds.

### Settings
`investigator_max_turns: int = Field(4, ge=1)`, `proposal_output_max_chars: int = Field(2000, gt=0)`, `logbook_review_max_attempts: int = Field(2, ge=1)`.

## Design notes
- **Why a pipeline (ADR-0009).** The triggers are known after `decide`; code picks the steps, so scripts stay linear and cost predictable. Reading logbooks is the only free-text judgment, so it is the only extra agent.
- **Blast radius.** The reader cannot write, the writer never reads a logbook. Two servers make the lists physical; 010 adds hooks on top.
- **One end-of-turn path.** The reminder and the output check are the same shape (a note once, then an exhausted outcome); one `EndReview` keeps a single branch in the loop and one seam for 010 (on-stop hooks) and 011 (validated output).
- **Why reuse `Coordinator`.** 007's extension point: one loop with an allowlist; budget, retries and append-only history stay in one place. Renaming it `AgentLoop` is a follow-up, not done here (churn across 007/008 tests).
- **Control in `agents` behind `CitationCheck`.** Validation sits next to its schema; the composition root passes `LogbookStore`, so citations still go through `verify_citation`.
- **Steps own their agent.** `InvestigatorStep` and `CoordinatorStep` own frame, task or brief and loop; the pipeline only orders them and picks the reason, which keeps 007/008 pipeline tests on small fakes.
- **Marks after the coordinator (Q-53).** A review succeeds only if its proposals reached a coordinator that finished or applied all of them, so the mark waits for that outcome; it is still written inside the unit, before `finish`, and an abort leaves none.
- **The book on the frame.** It lives exactly as long as the snapshot; it is the only owner of applied state, and the trace reads it.
- **Re-verifying in `apply_proposal`.** Redundant today, but one write path identical to 008's at the cost of one in-memory check.
- **Review rows are code writes.** The single agent writer stays the coordinator (ADR-0003); like the lifecycle, review rows are written by code in the unit.
- **Follow-ups for ADR-0009:** spec 010's allowlist excludes `set_cause`, `raise_severity`, `lift_severity_raise` (X9); structured output and caching (011); trend (016); `Coordinator` → `AgentLoop`.

## Test strategy
- **Unit, no I/O:** proposal types (E1), control (E2–E4, IF `LogbookStore`), task (E6), prompts and lists (E7, E8), review rules (E11), settings (E13), perspective builders (E15), brief (E16), trace (E17).
- **Loop:** E5 with a fake tool port and a fake `EndReview`; 007 E8 covers `MissingTexts`.
- **Tools through `ToolClient`:** E9, E10, E14d. **Registry:** E12. **Store:** E14a–c.
- **Step:** E25 (`InvestigatorStep` on FakeModel, IF logbooks, `:memory:` registry inside `processing`).
- **Integration** (`tests/integration/test_multi_agent_runner.py`): E18–E22, E24 on IF, file-backed registry, recording notifier.
- **Imports:** E23. Helpers: `incident_builders`, `incident_runs`, `agent_builders` (`tool`, `tools_reply`, `end`; new `out(*proposals)` and proposal builders).

## Risks
- **Haiku wraps JSON in prose:** one correction; the fence is tolerated; R17 measures the fallback rate.
- **Re-run after a partial apply (X1):** the second attempt costs a run and may end declined; bounded by the cap.
- **Turn cap 4 with several pending logbooks:** parallel tool calls fit; `fallback:turn_cap` shows it.
- **Test churn:** limited to the Acceptance list; 008's integration keeps its notices and registry rows.
