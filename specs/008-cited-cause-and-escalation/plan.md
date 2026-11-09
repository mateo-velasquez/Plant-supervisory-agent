# 008 · Cited cause and logbook escalation — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `domain/causes.py` | Adds | `CauseScope`, `CitedCause`, `ActiveCause`, `active_cause_id_for`. |
| `domain/notices.py` | Adds | `notice_brief_item` (shared by the brief and judgment results). |
| `cases/registry/schema.py`, `sqlite.py` | Changes | `SCHEMA_V2` (frozen), `MIGRATION_V2_TO_V3`, `SCHEMA` = both, `SCHEMA_VERSION` 3; `registry.causes`. |
| `cases/registry/causes_repo.py` | New | `CauseStore` protocol, `SqliteCauseRepository`. |
| `cases/causes.py` | New | Pure scope rules: `Candidate`, `matches`, `same_cause`, `link_targets`. |
| `cases/ledger.py` | New | `CauseLedger` (R3–R11 rules over the store) and its refusals. |
| `cases/facts.py`, `notice_builder.py`, `templates.py` | Changes | Cited cause on `CaseFacts`, notices and template text (R12). |
| `cases/draft.py` | Adds | `NoticeDraft.rebase` (R13). |
| `runner/pipeline.py` | Changes | Links and raises in `decide`, `redecide`, new `SnapshotDecision` fields. |
| `runner/judgment.py` | New | `SnapshotWriter` protocol, `SnapshotJudgment` adapter, `judgment_factory`. |
| `runner/agent_pipeline.py` | Changes | Closing trigger, writer in the frame, failure check, `decision_reason`. |
| `mcp_server/context.py` | Adds | `JudgmentResult`, `CauseWriter`, `RaiseWriter`, frame fields and `SnapshotFrame.with_writer`. |
| `mcp_server/write_tools.py`, `server.py` | Adds | `set_cause`, `raise_severity`, `lift_severity_raise`; `WRITE_TOOLS`. |
| `agents/loop.py`, `brief.py`, `factory.py`, `prompts/coordinator.md` | Changes | Stop rule, `causas_activas`, tool list, prompt v2. |
| `telemetry/trace.py` | Changes | Stored, nullable `decision_reason`. |
| `evaluation/golden.py`, `results.py`, `summary.py`, `cli.py` | Changes | R18 check; `Section.CAUSES`; causes in the summary; logbooks for run evidence. |
| `evaluation/causes.py` | New | `score_causes`, `cited_logbooks`. |
| `evals/agent_days_1_7.py` | New | R22 user-run script. |
| `tests/fixtures/incidents/`, `tests/incident_builders.py` | New | IF calendar, plan, logbooks; snapshot writer and `incident_context()`. |

## Types and interfaces

### `CauseScope` / `CitedCause` / `ActiveCause`
Frozen models in `domain/causes.py`:
- `CauseScope(modelo: Model, etapa: Stage, mercado: Market | None)`, with `describe() -> str` (`Pickup in montaje, any market`, `SUV in calidad, Europa`).
- `CitedCause(categoria: CauseCategory, etapa: Stage, evidence: Evidence, set_at: str, active_cause_id: str | None = None)`; `categoria` ≠ `no_declarada`; property `cause -> Cause`.
- `ActiveCause(active_cause_id: str, categoria: CauseCategory, scope: CauseScope, opened_at: str, opened_by: Evidence, lifted_at: str | None = None, lifted_by: Evidence | None = None)`; `categoria` ≠ `no_declarada`; `lifted_at` and `lifted_by` both set or both `None`; property `in_force`.
- `def active_cause_id_for(snapshot_id: str, n: int) -> str` → `S010-causa-1`.

### Registry v3
- `active_causes(active_cause_id PK, seq INTEGER UNIQUE, categoria CHECK <> 'no_declarada', modelo, etapa, mercado NULL, opened_at, opened_bitacora, opened_fragmento, lifted_at NULL, lifted_bitacora NULL, lifted_fragmento NULL, CHECK lifted trio all-or-none)`, with a partial unique index on `(modelo, etapa, COALESCE(mercado, ''))` `WHERE lifted_at IS NULL` (R5 check 3 backstop). `seq` = `1 + COALESCE(MAX(seq), 0)`, computed in the insert.
- `active_cause_links(active_cause_id REFERENCES active_causes, case_id REFERENCES cases, linked_at, PK both)`.
- `case_causes(case_id PK REFERENCES cases, categoria CHECK <> 'no_declarada', etapa, bitacora, fragmento, set_at, active_cause_id NULL REFERENCES active_causes)`.
- `schema.py`: `SCHEMA_V2_BODY` (the 004 tables, frozen), `MIGRATION_V2_TO_V3_BODY` (the three `CREATE`s); `SCHEMA` = `BEGIN; <v2 body> <migration body> PRAGMA user_version = 3; COMMIT;` and `MIGRATION_V2_TO_V3` = `<migration body> PRAGMA user_version = 3;`. One source for the v3 tables; E2e pins it.
- `SqliteRegistry.__init__`: 0 → `SCHEMA`; 2 → the migration inside an explicit `BEGIN IMMEDIATE` … `COMMIT` (statements executed one by one, since `executescript` would commit on its own), and on any exception `ROLLBACK`, close, re-raise; 3 → open; anything else → `ValueError(f"{path}: schema version {v}, expected 3")` before any write.

### `CauseStore` / `SqliteCauseRepository`
`registry.causes`, on the shared session. Writes take the snapshot id and go through `session.require_open`.
- Reads: `in_force() -> tuple[ActiveCause, ...]` (by `seq`); `get_active(active_cause_id) -> ActiveCause | None`; `opened_count(snapshot_id) -> int`; `links(ids: Collection[str]) -> dict[str, tuple[str, ...]]`; `cited(case_ids: Collection[str]) -> dict[str, CitedCause]`.
- Writes: `open(cause: ActiveCause) -> None`; `lift(active_cause_id, snapshot_id, evidence) -> None`; `link(active_cause_id, case_id, snapshot_id) -> None` (idempotent); `set_cited(case_id, cause: CitedCause) -> None` (upsert; `cause.set_at` must be the open snapshot). There is no delete: attached causes stay (Q-30, Q-38).
- `CauseStore` is the `Protocol` of these methods, re-exported from `cases.registry` like `CaseRepository`.

### `Candidate` / `matches` / `link_targets`
`cases/causes.py`, pure:
- `Candidate(case: Case, stage: Stage | None)`: frozen dataclass; `stage` is the Q-32 bottleneck.
- `def matches(scope: CauseScope, combination: Combination, stage: Stage | None) -> bool` (R6).
- `def same_cause(cited: CitedCause, categoria: CauseCategory, etapa: Stage) -> bool`.
- `def link_targets(cause: ActiveCause, candidates: Sequence[Candidate], cited: Mapping[str, CitedCause], linked: Collection[str]) -> tuple[str, ...]`: matching candidates not yet linked to `cause`, minus those with a different cited cause, in candidate order.

### `CauseLedger`
`cases/ledger.py`: `CauseLedger(store: CauseStore, cases: CaseLookup, shifts: Sequence[Shift])`, where `CaseLookup` is a protocol with `get_case`. Every method checks first and writes after, so a refusal writes nothing.
- `raised(cases: Sequence[Case]) -> frozenset[Combination]`: combinations of the given cases linked to a cause in force (R10).
- `recheck(snapshot_id, candidates: Sequence[Candidate]) -> bool`: R7 for every cause in force, in `seq` order, with R8 attachment; returns whether a link was added.
- `set_cause(snapshot_id, case_id, cause: Cause, evidence: Evidence, candidates: Sequence[Candidate]) -> None`: R3 checks 3–6 (`candidates` are the evaluated cases).
- `raise_severity(snapshot_id, categoria, scope, evidence, candidates: Sequence[Candidate]) -> RaiseOutcome(active_cause_id: str, linked: tuple[str, ...])`: R5 check 3, R6, R8.
- `lift(snapshot_id, active_cause_id, evidence) -> None`: R9 checks 1, 2, 4; it writes only `lifted_*`.
- `in_force_view() -> tuple[tuple[ActiveCause, tuple[str, ...]], ...]` and `cited(case_ids) -> Mapping[str, CitedCause]` (kept as thin reads so `runner` depends on the ledger only).
- Refusals (`RejectedRequest`): `CaseNotFound` (`unknown case <id>`), `CaseNotEvaluated`, `CauseAlreadySet`, `CauseFromRaise`, `DuplicateRaise`, `UnknownActiveCause`, `RaiseAlreadyLifted`, `LiftNotLater`. "Later" compares `calendar_order` positions of the two shifts.

### Notices with a cited cause
- `CaseFacts` gains `cited: CitedCause | None = None`.
- `build_snapshot_notices(delta, metrics, cause_rows, close, cited: Mapping[str, CitedCause] | None = None)`; `case_notice` uses `cited.cause` and `(cited.evidence,)` when set, else `default_cause` and `()`.
- `cause_text` gains the declared sentence and a category → text map (R12); the 004 branches are unchanged.

### `NoticeDraft.rebase`
`rebase(notices: SnapshotNotices) -> tuple[Notice, ...]`: replaces the draft's notices, keeps or drops texts by R13 (equality on `model_dump(mode="json")` without `texto`), recomputes required ids, and returns the pending notices that appeared or changed (for `avisos`).

### `SnapshotDecision` / `ThresholdPipeline`
- `SnapshotDecision` gains `delta: CaseDelta | None = None`, `candidates: tuple[Candidate, ...] = ()` and `in_force: tuple[tuple[ActiveCause, tuple[str, ...]], ...] = ()` (defaults keep 007 fakes valid).
- `ThresholdPipeline(..., ledger: CauseLedger | None = None)`; `from_registry(registry, ctx, ledger: CauseLedger | None = None)`; with no ledger, raises are empty and no link is made (X2).
- Shared step `_lifecycle(snapshot_id, metrics, cases: Sequence[Case])`: `track` with `raised(cases)` → candidates = each delta case with the bottleneck of `deviation_rows` (the same `ValueError` when a case has none) → `ledger.recheck` → if it added a link, `track` again with the new raises and rebuild the candidates. One re-run suffices (R10).
- `decide`: metrics → releases → `_lifecycle` with the active cases read before `track` (cases opening at N are not linked yet, so the first `track` opens them unraised) → closing glue → `cited` → build.
- `redecide(decision) -> SnapshotDecision`: `_lifecycle` with `decision.delta.cases` → closing glue → `cited` → build. Same metrics, same unit (Q-27). `finish` is unchanged.

### `JudgmentResult` / `CauseWriter` / `RaiseWriter`
`mcp_server/context.py`:
- `JudgmentResult(case_ids: tuple[str, ...], active_cause_id: str | None, lifted_at: str | None, changed: tuple[Notice, ...], pending: tuple[str, ...])`.
- `CauseWriter`: `set_cause(case_id: str, cause: Cause, evidence: Evidence) -> JudgmentResult`.
- `RaiseWriter`: `raise_severity(categoria: CauseCategory, scope: CauseScope, evidence: Evidence) -> JudgmentResult`; `lift(active_cause_id: str, evidence: Evidence) -> JudgmentResult`.
- `SnapshotFrame` gains `causes: CauseWriter | None = None` and `raises: RaiseWriter | None = None`. `classmethod with_writer(snapshot_id, at, metrics, units, writer: FrameWriter) -> SnapshotFrame` sets `notices`, `causes` and `raises` to the same object; `FrameWriter` is the protocol joining the three. The pipeline builds frames only through it.
- **Why on the frame, not on `ToolContext`:** the writer needs the snapshot's decision and draft, which exist only per snapshot. `ToolContext` is frozen per run and would need a mutable slot, a second holder that can fall out of sync. The frame is entered after 007's R11 check and left before `finish`, so no judgment write can happen outside the open unit. This revises 007's note that per-run writers would go on `ToolContext`.

### Judgment tools
- `write_tools.set_cause(ctx, frames, case_id, categoria: CauseCategory, etapa: Stage, bitacora, fragmento) -> str`; `raise_severity(ctx, frames, categoria, etapa, modelo: Model, mercado: Market | None, bitacora, fragmento) -> str`; `lift_severity_raise(ctx, frames, active_cause_id, bitacora, fragmento) -> str`.
- Each: frame writer (`None` → `NoJudgmentWriter`, `no judgment is being recorded at this snapshot`) → R3/R5 check 1 (`CauseIsDefault`, two messages) → `ctx.logbooks.verify_citation(bitacora, fragmento, frame.snapshot_id)` → writer. The fragment is passed with its ends stripped.
- Results: compact JSON with the R3/R5/R9 keys; `avisos` = `[notice_brief_item(n) for n in result.changed]`, `pendientes` = `result.pending`.
- `server.WRITE_TOOLS = ("set_cause", "raise_severity", "lift_severity_raise", "emit_alert", "emit_shift_report")`; async wrappers as in 007; `mercado: Market | None = None`.

### `SnapshotWriter` / `SnapshotJudgment`
`runner/judgment.py`:
- `SnapshotWriter(Protocol)`: `FrameWriter` + `missing()`, `required()`, `written()`, `final() -> SnapshotDecision`, `failure() -> Exception | None`.
- `JudgmentFactory = Callable[[SnapshotDecision], SnapshotWriter]`; `def judgment_factory(steps: Redecider, ledger: CauseLedger, max_chars: int) -> JudgmentFactory`.
- `SnapshotJudgment(steps: Redecider, decision: SnapshotDecision, ledger: CauseLedger, max_chars: int)` implements it. A judgment write: ledger call (refusals propagate) → `decision = steps.redecide(decision)` → `changed = draft.rebase(decision.notices)` → `JudgmentResult`. Candidates come from `decision.candidates`.
- **Failure (R10):** every write, `emit_*` included, runs inside one guard: a `RejectedRequest` propagates; any other `Exception` is stored (first only) and re-raised. While a failure is stored every write raises `WritesClosed` (`writes are closed at <snapshot> after an internal error`). No savepoint: the abort rolls back the whole unit.
- `final()`: the last decision with `draft.build()` as notices.
- `Redecider` protocol: `redecide(decision) -> SnapshotDecision`; `ThresholdPipeline` satisfies it.

### `AgentPipeline`
- `NoticeSteps` gains `redecide`. `AgentPipeline(steps, unit, frames, coordinator, trace, prices, judgment: JudgmentFactory)` (replaces `max_chars`; no `None` branch). 007 pipeline tests pass a small fake writer over `NoticeDraft` (`draft_builders.FakeSnapshotWriter`).
- `process`: `decide` → writer → reason: `text_needed` if `required()`, else `closing_review` at a closing snapshot, else `no_text_needed` (skip as in 007) → R11 check → `SnapshotFrame.with_writer(...)` → `anyio.run` → **if `writer.failure()` is set, raise it** → `finish(writer.final())` → stage the line with the reason and the final ids.
- The abort path writes the line with the reason already taken; when `decide` raised, `decision` `skip` and `decision_reason` `None` (R14).
- `render_brief` receives `decision.in_force`.
- `build_agent_pipeline` builds one `CauseLedger` and passes it to `ThresholdPipeline.from_registry` and `judgment_factory`.

### Brief, loop and trace
- `render_brief(snapshot_id, turno_id, position, alerts, news, active_causes: Sequence[tuple[ActiveCause, Sequence[str]]] = ())`; items from `notice_brief_item`; new instruction line (R15).
- `TextProgress` gains `required() -> tuple[str, ...]`; after `tool_use` the loop returns `done` only if `required()` and not `missing()`.
- `TraceLine.decision_reason: Literal["text_needed", "closing_review", "no_text_needed"] | None` becomes a stored field; `build_line(..., decision_reason=...)`. Old trace files still parse (the computed field was serialized).
- `COORDINATOR_TOOLS` = the R15 order, literal names.

### `score_causes`
- `results.py`: `Section.CAUSES = "causes"`; `CAUSE_ERRORS` = the R19 error keys.
- `evaluation/causes.py`: `def score_causes(run: RunOutput, golden: GoldenSet, shifts: Sequence[Shift], logbooks: Mapping[str, str], capabilities: frozenset[Capability]) -> tuple[Result, ...]` (one result per golden cause, `where` = target snapshot or shift); `def cited_logbooks(run: RunOutput, golden: GoldenSet) -> frozenset[str]`.
- `summary.py`: `EvalSummary.causes: tuple[Result, ...] = ()`; `evaluate(..., logbooks: Mapping[str, str] = {})`; table row and JSON section; `gating_errors` adds gated cause errors.
- `cli.run_eval`: after loading, `read_logbook_texts(logbooks_dir, cited ∩ known − refused, policy)` once, then `evaluate`.
- `golden.py`: `_check_availability(causes, alerts, calendar)` between `_check_across` and `_check_evidence`.

### Prompt v2
`agents/prompts/coordinator.md` with the R16 headings; title `# Coordinator prompt v2`.

## Design notes
- **Code computes, the model judges (ADR-0002).** The model supplies category, stage, scope fields and citations; code verifies citations, computes candidates, links, raises, lifecycle and notices. The model never names the cases a raise reaches.
- **Why the adapter lives in `runner`.** Re-deciding means calling `track` and the closing glue, which is runner work (007 extension point). `mcp_server` sees only the protocols; `cases.ledger` holds the rules and is testable without the model or the server.
- **Why the adapter carries failures.** The SDK turns any non-refusal exception into a generic tool error, so without the stored failure `finish` would commit half-written rows. Closing writes after a failure keeps the model from building on a broken state.
- **Links in one place.** The lifecycle step only reads links (`raised`); the R7 re-check and the raise are the only writers, and a re-run follows any new link, so openings and re-checks share one path (no special first-`track` set).
- **Why links are stored.** Sticky links survive the bottleneck moving, and they rebuild "why was this case raised" from the registry (FR-38).
- **Re-decide cost.** Each judgment write re-runs `track` (at most twice) and the notice build: nine combinations, a few cases.
- **Determinism.** Active-cause ids depend only on the order of accepted raises in a snapshot; the model is the only nondeterministic input.
- **Rollback is resumability.** Every judgment row is written inside `processing`; an abort leaves nothing (E22, E33).
- **Stop rule.** Keeping 007's "done without a closing request" saves a request when texts are required; the prompt asks for judgment first, and a review call runs to `end_turn`.
- **Deferred (optional review items):** a verified-evidence type returned by `LogbookStore`, and removing the ledger's thin reads.

## Test strategy
- **Unit, no I/O:** `domain/causes.py` (E1), `matches` (E4), templates and builder (E15), `NoticeDraft.rebase` (E16), `render_brief` (E19), prompt (E20), `score_causes` (E24–E29, golden sets built as in 005).
- **Registry:** E2, E3 on `tmp_path` files and `:memory:`.
- **Ledger:** E6, E8, E9, E10 on `:memory:` with 003 builders, inside `processing`.
- **Pipeline without the model:** E11–E14, E34 through `ThresholdPipeline` and the ledger on IF data.
- **Tools through `ToolClient`:** E5, E7 with recording fake writers and the IF logbook store.
- **Adapter:** E17 with real steps on a `:memory:` registry.
- **Agent pipeline and loop:** E18 with a fake writer, fake steps and `FakeModel` (sync tests).
- **Integration** (`tests/integration/test_judgment_runner.py`): E21, E22, E33 on IF, file-backed registry, recording notifier.
- **Evaluation:** E23 (synthetic calendar), E30, E31; **imports:** E32.
- Tests cite E ids; helpers come from `builders`, `notice_builders`, `agent_builders`, `draft_builders` and `incident_builders`.

## Risks
- **Haiku skips judgment or emits first:** the prompt orders judgment first; R22 and the cause metric show it.
- **Over-broad scope:** a model-chosen `mercado: null` on a market-specific logbook raises too many cases; the per-snapshot re-check (Q-49) widens the effect over time. Evals catch it.
- **Turn cap:** a closing call that reads logbooks, raises and writes may need more turns; `agent_max_turns` stays 8, the trace shows `fallback:turn_cap`, and judgment writes survive it.
- **Rebase surprises:** a cause change resets a written text; `avisos` and `pendientes` tell the model what to rewrite.
- **007 test churn:** limited to the expectations listed in the spec's Acceptance.
