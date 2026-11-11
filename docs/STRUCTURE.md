# Repository structure

Target layout. Modules are created when their spec is implemented; this file is updated in the same PR.

```
.
├── CLAUDE.md                 # rules for Claude Code
├── README.md                 # what it solves, how to run, design decisions (why)
├── pyproject.toml / uv.lock  # dependencies and tool config
├── .env.example              # configuration template
├── .pre-commit-config.yaml   # local hooks: ruff, mypy, gitleaks, uv lock, .env guard
├── .gitattributes            # LF line endings on every OS
├── .claude/                  # Claude Code config (ADR-0006, ADR-0012)
│   ├── agents/               # spec-writer, test-writer, domain-implementer, reviewer, design-reviewer, eval-curator
│   ├── skills/               # new-spec, implement-spec, verify-criteria, new-adr, check, pr-handoff
│   ├── hooks/guard.py        # pre: guard rules · post: format edited .py
│   └── settings.json         # hook wiring + permission rules (settings.local.json is personal, ignored)
├── .github/
│   ├── workflows/ci.yml      # lint, format, types, tests + coverage (Ubuntu, Windows)
│   ├── workflows/secrets.yml # gitleaks over full history
│   ├── dependabot.yml        # weekly uv + GitHub Actions updates
│   └── pull_request_template.md
├── src/plant_monitor/
│   ├── config.py             # Settings (pydantic-settings)
│   ├── domain/               # pure types: Unit, Snapshot, Combination, Severity, CaseState, Cause, Notice, Report
│   ├── ingestion/            # loaders (CSV with BOM, JSON), schema validation, arrivals, content hash
│   ├── metrics/              # thresholds, lookup tables, progress, cumulative plan, gap, delay, bottleneck, min severity
│   ├── cases/                # lifecycle state machine, novelty rules, registry (repository over SQLite)
│   ├── logbooks/             # logbook store, availability by shift, verbatim citation check
│   ├── mcp_server/           # own in-process MCP server and ToolClient: read tools, write tools, criteria prompt
│   ├── agents/               # agentic loop, agent roles + tool allowlists, factory, system prompts
│   ├── hooks/                # pre-tool, post-tool and on-stop guards
│   ├── notify/               # notifier port + adapters (console, file per shift)
│   ├── telemetry/            # token/cost accounting, trace log
│   ├── evaluation/           # golden loader, alert/news/noise scoring, summary, eval CLI (ADR-0011)
│   └── runner/               # series runner (order, dedupe, anomaly checks, unit of work) and CLI entry point
├── tests/
│   ├── unit/                 # one module per domain rule; no I/O, no LLM
│   ├── integration/          # runner + registry + MCP with a fake model
│   ├── dev_hooks/            # tests for .claude/hooks/guard.py
│   ├── fixtures/             # small synthetic dataset (versioned)
│   └── builders.py           # shared snapshot builders (`from builders import ...`)
├── evals/
│   ├── golden/               # hand-verified expected notices per day (days 1–7) + incidents.md catalog
│   ├── run_eval.py           # thin script over evaluation.cli.run_eval
│   ├── smoke_days_1_7.py     # threshold-only run of days 1–7 into outputs/evals/smoke-<ts>/
│   ├── agent_days_1_3.py     # on-demand run of days 1–3 with the coordinator and Haiku (paid; user-run)
│   └── agent_days_1_7.py     # on-demand run of days 1–7, investigator + coordinator, cost per agent (paid; user-run, 008/009)
├── specs/
│   ├── stories/              # user stories with Gherkin acceptance criteria
│   ├── _template/            # spec / plan / tasks templates
│   └── NNN-feature/          # one folder per feature (spec.md, plan.md, tasks.md)
├── docs/
│   ├── requirements.md       # FR / NFR with IDs
│   ├── roadmap.md            # specs in order, priorities, dates
│   ├── agent-capabilities.md # FR-28 table: tools, inputs, outputs and writes per agent (009)
│   ├── STRUCTURE.md          # this file
│   ├── adr/                  # architecture decision records
│   └── diagrams/             # Mermaid diagrams
├── data/                     # real data, NOT versioned (only README)
└── z_helps/                  # local support material, NOT versioned
```

## Implemented modules

| Module | Spec | Contents |
|---|---|---|
| `domain/enums.py` | 001, 002 | `Severity` (ordered), `Stage` (downstream `rank`), `Market`, `Model`, `PRODUCTION_STAGES`, `ShiftPosition`, `AnomalyKind` |
| `domain/models.py` | 001, 002 | Frozen input models, `Combination`, `CombinationMetrics`, `all_combinations()`, `Anomaly`, `SnapshotCommit` |
| `domain/calendar.py` | 002, 005, 006 | `snapshot_position` (shift row and `ShiftPosition`); `calendar_order`; `closed_shifts` (R1); `HeldOutPolicy` (`from_calendar`, refused sets while closed) |
| `domain/verbatim.py` | 006 | `normalize_whitespace`, `contains_verbatim` (shared by the golden loader and the logbook citation check) |
| `domain/errors.py` | 006 | `RejectedRequest`: base of refusals whose message is shown to the model (R13) |
| `domain/proposals.py` | 009 | Investigator output contract: `CauseState` (`estado_causa`), `SetCauseProposal`, `RaiseProposal`, `LiftProposal`, `Proposal`, `InvestigatorOutput`, `ValidatedProposal` (code-assigned id) |
| `domain/perspectives.py` | 009 | `GapPerspective`, `ShipmentPerspective`, `BottleneckPerspective`, `CasePerspective` (brief `perspectivas`; spec 016 adds `tendencia` to the gap) |
| `domain/numbers.py` | 009 | `DECIMALS` and the display rounding helpers shared by the tool views and the perspectives |
| `logbooks/store.py` | 006, 009 | `LogbookLoader`, `Logbook`, `LogbookStore` (`available`, `get` with R3 check order, `verify_citation`; `missing`, and a vanished file is the `LogbookMissing` refusal, 009 R8); loads only through the injected loader (R4) |
| `logbooks/errors.py` | 006, 009 | `UnknownLogbook`, `LogbookHeldOut`, `LogbookNotAvailable`, `EmptyFragment`, `FragmentNotFound`, `LogbookMissing` (009) (`RejectedRequest` subclasses) |
| `logbooks/render.py` | 006 | `render_logbook`: the delimited `<bitacora>` block with colliding tags escaped (R6, X1) |
| `logbooks/__init__.py` | 006 | Re-exports the store, the errors and `render_logbook` |
| `mcp_server/__init__.py` | 006 | Package docstring only |
| `mcp_server/context.py` | 006, 007, 008, 009 | `SnapshotFrame` (with `notices: NoticeTextWriter | None`, 007; `causes`, `raises`, `with_writer`, 008; `proposals: ProposalBook | None`, 009), `ProposalBook` (`get`, `mark_applied`; `UnknownProposal`, `ProposalApplied`, 009), `NoticeTextWriter` protocol (007), `JudgmentResult`, `CauseWriter`, `RaiseWriter`, `FrameWriter` (008), `FrameHolder` (`current`, `entered` raises `ValueError` on nesting; R7), `NoCurrentSnapshot`, `UnknownCase`, `CaseReader` (read-only protocol, R14), `ToolContext` |
| `mcp_server/budget.py` | 006 | `to_text` (compact JSON), `check_budget`, `fit_list` (drops list items from the end through a `rebuild` callable), `OverBudget` (R12) |
| `mcp_server/views.py` | 006 | Output view models in Spanish field names: `AvailableLogbook`, `LogbooksView`, `DeviationsView`, `ActiveCasesView`, `CaseView`, `DelayedUnitsView` and their rows; pure builders (`deviations_view`, `active_cases_view`, `case_view`, `delayed_units_view`) round floats (R8–R11) |
| `mcp_server/types.py` | 007 | `ToolSpec`, `ToolOutcome`: plain dataclasses with no `mcp` import, re-exported by `client.py`, so `agents` stays SDK-free |
| `mcp_server/write_tools.py` | 007, 008, 009 | 009: `apply_proposal(propuesta)` fills the 008 writer call from a validated proposal (re-verified citation, `match` + `assert_never`), `NoProposalBook`. 007/008: `emit_alert`, `emit_shift_report` (`NewsText`): sync functions that write `texto` through the frame's `NoticeTextWriter`; `NoNoticeWriter` refusal (R8, R9). 008: `set_cause`, `raise_severity`, `lift_severity_raise` verify the citation, then call the frame's `CauseWriter`/`RaiseWriter`; `NoJudgmentWriter`, `CauseIsDefault` |
| `mcp_server/read_tools.py` | 006 | The six read tools as pure sync functions `(ctx, frames, ...) -> str`; no `mcp` import; each applies `check_budget`, or `fit_list` for the truncatable lists of `get_case` and `get_delayed_units` (R12) |
| `mcp_server/server.py` | 006, 007, 009 | `READ_TOOLS`, `WRITE_TOOLS` (incl. `apply_proposal`; the 008 judgment tools stay registered but no agent list offers them, 009), `build_server(ctx, frames, tools=READ_TOOLS)`: async wrappers that map `RejectedRequest` to `ToolError` (R13) |
| `mcp_server/client.py` | 006 | `ToolClient` (async context manager over the in-process SDK client), `ToolSpec`, `ToolOutcome`: plain dataclasses, the only door `agents` uses (D4) |
| `domain/cases.py` | 003 | `CaseState`, `CaseEvent`, `effective_severity` (the only place it is computed), `case_id_for`, `Case`, `CaseHistoryRow` |
| `domain/causes.py` | 004, 008 | `CauseCategory` (§6 catalog), `Cause` (`etapa` nullable, Q-17), `Evidence`; `CauseScope` (`describe`), `CitedCause`, `ActiveCause`, `active_cause_id_for` (008) |
| `domain/notices.py` | 004, 008 | Output contract: `NoticeType`, `Origin`, `Reason` (`motivo`, Q-31), `Notice`, `ActiveCaseRow`, `ShiftReport`, `PendingDelivery`, deterministic `notice_id_for` / `report_id_for`; `notice_brief_item` (008, shared by the brief and the judgment tools) |
| `cases/lifecycle.py` | 003 | Pure lifecycle: `next_state` transition table, `Observation`, `Step`, `step`, `mark_reported` |
| `cases/facts.py` | 004, 008 | `CaseFacts`: a case plus its snapshot metrics, cause row (Q-32) and optional cited cause (008) |
| `cases/reviews.py` | 009 | Pure logbook-review rules: `ReviewMark` (`revisada`, `reintento`, `sin_revisar`), `LogbookReview`, `pending_logbooks`, `review_succeeded` (Q-53), `next_review` (2-attempt cap, Q-52) |
| `cases/perspectives.py` | 009 | `gap_perspective(case, now, history)`: gap now and at the case's last report, rounded |
| `cases/registry/reviews_repo.py` | 009 | `SqliteReviewStore` (`registry.reviews`): logbook review rows, written inside `processing` (schema v4) |
| `cases/causes.py` | 008 | Pure scope rules of active causes: `Candidate`, `matches`, `same_cause`, `link_targets` |
| `cases/registry/causes_repo.py` | 008 | `CauseStore` protocol and `SqliteCauseRepository` (active causes, links, cited causes; registry schema v3) |
| `cases/ledger.py` | 008 | `CauseLedger`: `set_cause`, `raise_severity`, `lift`, `raised`, `recheck` (Q-02, Q-11, Q-29, Q-30, Q-48, Q-49), checks before writes; refusals (`CaseNotEvaluated`, `CauseAlreadySet`, `DuplicateRaise`, `LiftNotLater`, ...) |
| `cases/novelty.py` | 004 | Pure §4 rules, reused by spec 010's hooks: `alerts_for` / `alerted_case_ids` (last delta only), `news_reasons` / `expected_news` (`NewsReason`, `NewsItem`), `report_set`, `active_rows`, `case_order` |
| `cases/notice_builder.py` | 004, 008 | `reasons_for` / `origin_for` (Q-31), `default_cause` (Q-17, Q-32), `case_notice`, `build_snapshot_notices` (one decision per evaluated case, the report at closing; cited causes override the default, 008), `ShiftClose`, `SnapshotNotices` |
| `cases/templates.py` | 004, 008 | Deterministic Spanish `texto` (template fallback) and number formatting; declared-cause sentence (008) |
| `cases/registry/` | 003, 004, 005, 008, 009 | Package re-exporting the names below. `schema.py` (`SCHEMA_V2_BODY`, one migration step per version in `STEPS`, `migration_from`, `SCHEMA` = frozen v2 + steps, `SCHEMA_VERSION` = 4; v2 and v3 files migrate in place, 008/009), `session.py` (`Session`: connection, open unit, write guard, `savepoint`), `sqlite.py` (`SqliteRegistry`: `user_version`, the only unit of work `processing`, `ProcessedStore`), `cases_repo.py` (`SqliteCaseRepository` incl. `resolved_unreported` and `last_deviation_row`, `CaseRepository` protocol), `releases.py` (`SqliteReleaseStore`), `notices.py` (`SqliteNoticeStore` = `registry.notices`: decisions and delivery outbox, ADR-0010; module-level `read_deliverables(path)`, read-only `mode=ro`, same `DELIVERABLE_FILTER` as `pending()`) |
| `cases/draft.py` | 007, 008 | `NoticeDraft`: in-memory draft of a snapshot's notices (`required`, `missing`, `write_alert`, `write_news`, `build` through the validators; `rebase` keeps an alert text while its notice is unchanged and keeps report texts only as a unit: they all survive or all reset when the news list changes in any way, 008) and its `RejectedRequest` refusals (R8–R10) |
| `cases/tracker.py` | 003 | `CaseTracker.track` (lifecycle over the registry; re-runnable within a snapshot, Q-27) and `mark_reported`; `CaseDelta`, `TrackedEvent` |
| `config.py` | 003, 004, 005, 006, 007, 009 | Model, retry, loop, price and long-context settings and derived `traces_dir` (007); `investigator_max_turns`, `proposal_output_max_chars`, `logbook_review_max_attempts` (009); `tool_output_max_chars`, `logbook_max_chars` (006); `Settings.registry_path` = `output_dir / "registry.sqlite3"`, `Settings.notices_dir` = `output_dir / "notices"`; `heldout_open`, `heldout_first_shift`; derived `plant_dir`, `snapshots_dir`, `logbooks_dir`, `rules_dir`, `evals_dir` |
| `notify/port.py` | 004 | `Notifier` protocol (`alert`, `report`) |
| `notify/console.py`, `notify/file.py`, `notify/composite.py` | 004 | `ConsoleNotifier` (never fails on encoding), `FileNotifier` (atomic report per shift, idempotent `alertas.jsonl`), `CompositeNotifier` |
| `ingestion/errors.py` | 001 | `DataLoadError` and validation-message formatting |
| `ingestion/plant.py` | 001 | `load_plan`, `load_standards`, `load_shipments`, `load_shifts` (BOM, row checks, plan completeness) |
| `ingestion/rows.py` | 002, 005 | `iter_rows`: streaming CSV row reader (BOM, physical-line errors); `read_rows` = `list(iter_rows(...))` |
| `ingestion/held_out.py` | 005 | `check_ids`: refuses held-out shift and snapshot ids (`DataLoadError`) |
| `ingestion/logbooks.py` | 005, 009 | `read_logbook_texts`: shift logbook texts through the held-out guard (`utf-8-sig`, universal newlines); `LogbookFileMissing` for an absent file (009) |
| `ingestion/snapshot.py` | 001, 002 | `load_snapshot`, `parse_snapshot` (bytes, no filesystem) |
| `ingestion/hashing.py` | 002 | `content_hash`: lowercase hex SHA-256 of raw bytes |
| `ingestion/arrivals.py` | 002, 005 | `Arrival`, `load_arrivals` (`llegadas.csv`, sorted by `orden`); `load_arrivals_until` (streams up to the allowed snapshots) |
| `runner/ports.py` | 002, 004 | `ProcessedStore` (unit of work over a `SnapshotCommit`), `SnapshotPipeline` and `PostCommit` protocols |
| `runner/outbox.py` | 004 | `OutboxDispatcher` (`PostCommit`: ordered, at-least-once delivery after commit, ADR-0010) and the `PendingNotices` protocol |
| `runner/memory_store.py` | 002 | `InMemoryProcessedStore` |
| `runner/checks.py` | 002 | Pure anomaly checks: shift mismatch, future stage entry, unit identity |
| `runner/pipeline.py` | 004, 007, 008, 009 | `ThresholdPipeline` (`decide` → `SnapshotDecision`, `finish`; `process = finish(decide())`, 007; optional `ledger`, `redecide`, `SnapshotDecision.delta`/`candidates`/`in_force`, 008; `SnapshotDecision.cited`, 009), `shift_close`, `deviation_rows` and the `ReleaseLog`, `NoticeSink`, `NoticeCaseReader` protocols |
| `runner/agent_pipeline.py` | 007, 008, 009 | `AgentPipeline` (sequences decide → investigator step → coordinator step → failure check → review marks → single `finish`; Q-51 reasons; frame check against `current_snapshot()`; staged and aborted trace lines with per-agent records, 009), `OpenUnit`, `NoticeSteps`, `build_agent_pipeline` (composition root: two tool servers over one `FrameHolder`, ADR-0009) |
| `runner/perspectives.py` | 009 | `case_perspectives(decision, required, cases, plant)`: the brief's perspectives for the cases of the required notices, over `CaseReader` |
| `runner/bridge.py` | 009 | `run_in_frame`: frame entry, `anyio.run` and single-leaf exception-group unwrap (X5); imports `mcp_server.context` only |
| `runner/review_step.py` | 009 | `ReviewPlan`, `ReviewOutcome`, `LogbookReviewStep`, `InvestigatorStep` (plan, read-only run, review marks); imports `agents`, `cases`, `domain`, `logbooks`, `mcp_server.context`, `runner` |
| `runner/coordinator_step.py` | 009 | `CoordinatorStep`, `CoordinatorOutcome` (brief v3, proposal book, writer frame); imports `agents`, `domain`, `mcp_server.context`, `runner` |
| `runner/judgment.py` | 008 | `SnapshotJudgment` (draft + ledger behind one writer: ledger call → `redecide` → `rebase`; failure guard stores the first internal error and closes later writes with `WritesClosed`), `SnapshotWriter`, `Redecider`, `JudgmentFactory`, `judgment_factory` (R10, R13) |
| `runner/post_commit.py` | 007 | `PostCommitChain`: runs post-commit steps (trace flush, outbox) in order; a failing step is logged and never blocks the next |
| `agents/model.py` | 007 | Model port: content blocks, `Message`, `ModelRequest`, `ModelReply`, `ModelSession`, `ModelPort`, `ModelCallFailed` (no SDK types) |
| `agents/anthropic_model.py` | 007 | `AnthropicModel` (the only `anthropic` import): own retries with backoff (`RetryPolicy`, `backoff_delay`, `is_retryable`), `to_params`, `from_message` |
| `agents/fake_model.py` | 007 | `FakeModel`: scripted replies and token counts for tests (NFR-07) |
| `agents/loop.py` | 007, 008, 009 | `Coordinator` (the loop class of both agents: turns, stop conditions, tool errors, budget guard, append-only history; one end-of-turn path through `EndReview`, 009), `ToolPort`, `TextProgress`, `EndReview`, `MissingTexts` (007 reminder), `LoopOutcome` (incl. `fallback:invalid_output`), `LoopConfig`, `LoopLog` |
| `agents/brief.py`, `agents/factory.py`, `agents/prompts/coordinator.md` | 007, 008, 009 | `render_brief` (v3: `causas_activas`, `perspectivas`, proposals block via `render_proposals`), `render_reminder`, `cause_item`; `COORDINATOR_TOOLS` (four read tools, `apply_proposal`, two emit tools), `INVESTIGATOR_TOOLS` (four read tools), `load_prompt(name)`, `build_coordinator`, `build_investigator`; coordinator prompt v3 (009 R13) |
| `agents/control.py` | 009 | Code control of the investigator output: `CitationCheck` (satisfied by `LogbookStore`), `TaskCase`, `InvestigatorTask`, `ControlResult`, `check_output` (schema, size, `estado_causa`, scope, citation) |
| `agents/investigator.py`, `agents/prompts/investigator.md` | 009 | `render_task`, `ReviewLog`, `ProposalReview` (one correction round), `NothingRequired`; investigator prompt v1 |
| `telemetry/usage.py` | 007 | `Usage`, `PriceCard`, `cost_usd` (long-context ×5 card above 100k prompt tokens) |
| `telemetry/trace.py` | 007, 008, 009 | `TraceLine` (stored nullable `decision_reason`: `text_needed`, `proposals`, `investigator_only`, `no_text_needed`; `closing_review` still parses; `investigator` entry, `agents_run`, proposal lists, totals over both agents, 009), `InvestigatorRecord`, `_costed`, `AgentRunTotals`, `RunTotals.by_agent`, `build_line`, `abort_outcome`, `trace_path`, `TraceWriter` (stage, `after_commit`, `write_now`; logs its own `OSError`), `read_trace`, `run_totals` |
| `runner/series.py` | 002, 004 | `RunSummary`, `RunAborted`, `run_series` (order, dedupe, checks, delegate; optional `post_commit` at run start and after each commit) |
| `metrics/thresholds.py` | 001 | `Thresholds` and `load_thresholds` for `umbrales.yaml` |
| `metrics/tables.py` | 001 | `StandardsTable`, `ShipmentsTable` (bisect over cut-offs) |
| `metrics/progress.py` | 001, 002 | Distinct released units per combination; first release wins (Q-20) |
| `metrics/plan.py` | 001 | `cumulative_plan`, `gap_pct` |
| `metrics/delay.py` | 001, 002 | Projected yard arrival (elapsed clamped at 0, Q-19), reachable shipment, delay in days |
| `metrics/bottleneck.py` | 001 | Delayed units and bottleneck stage |
| `metrics/severity.py` | 001 | Gap, delay and minimum severity |
| `metrics/engine.py` | 001 | `PlantContext` and `compute_metrics` for one snapshot |
| `metrics/shipment.py` | 009 | `shipment_perspective`: delayed units, worst delay and assigned vs reachable shipment of one combination |
| `evaluation/output.py` | 005 | `RunOutput`: a run's deliverable alerts and shift reports |
| `evaluation/sources.py` | 005 | `load_run_output`: reads the registry outbox through `read_deliverables` and refuses held-out ids |
| `evaluation/golden.py` | 005, 008 | Golden YAML schema and `load_golden` (`GoldenSet`, `Capability`; keys `{modelo, mercado, abre_en}` → `case_id_for`; `covers`, `depends_on`, `requires`; justifications cite `criterio N`; verbatim evidence check at load; availability of golden evidence at the target notice, Q-01, 008) |
| `evaluation/results.py` | 005, 008 | `Result`, `Section` (incl. `CAUSES`), `tally`, `errors`, `ALERT_ERRORS`, `NEWS_ERRORS`, `CAUSE_ERRORS` |
| `evaluation/causes.py` | 008 | `score_causes` (FR-39 cause metric: category, stage, verbatim and readable evidence), `cited_logbooks` |
| `evaluation/scoring.py` | 005, 008 | `score_alerts`, `score_news`, `is_gated` (covered shifts only; `requires` gating and per-case release of extras) |
| `evaluation/noise.py` | 005 | `count_noise` (`RepeatedNews`, `NoiseScore`): §4 repeats re-derived without `cases.novelty`; duplicate alerts reported, not gating |
| `evaluation/summary.py` | 005, 008 | `EvalSummary` (with `causes`, 008), `evaluate`, `exit_code`, `render_table`, `write_summary` (`outputs/evals/eval-<ts>.json`) |
| `evaluation/timeline.py` | 005 | `CaseTimeline`, `case_timeline` (calendar order) |
| `evaluation/cli.py` | 005, 008 | `run_eval` (keyword-only; loads the logbooks the run notices cite, 008): exit 0 ok, 1 gated errors, 2 load error |

## Dependency rule
Dependencies point inward:

```
runner → agents → mcp_server → cases / metrics / logbooks → domain
                ↘ hooks ↗
runner → notify
notify, telemetry, ingestion → domain
evaluation → ingestion → domain
```

- `domain` imports nothing from the project.
- `ingestion` imports only `domain`. `runner` may import `ingestion`, `metrics`, `cases` (`runner/pipeline.py`) and `notify` (`runner/outbox.py`); `runner/checks.py` imports only `domain`. `runner/judgment.py` imports only `domain`, `cases`, `runner` and `mcp_server.context` (008).
- `notify` imports only `domain`; text is built in `cases/templates.py`, not by the channels.
- `cases` imports only `domain` and `metrics.thresholds` (checked per module). `SqliteRegistry` satisfies `runner`'s `ProcessedStore` structurally, without importing `runner`.
- `metrics` and `cases` never import `agents`, `mcp_server` or `anthropic`. The deterministic core is testable without the model.
- Only `agents/anthropic_model.py` imports `anthropic`, and only `mcp_server` imports `mcp`. `agents` imports only `domain`, `telemetry`, `config`, `agents` and `mcp_server.types`; the composition root (`runner/agent_pipeline.py`) wires `ToolClient` in-process (ADR-0013, ADR-0014).
- `runner/review_step.py`, `runner/coordinator_step.py`, `runner/perspectives.py` and `runner/bridge.py` may import what `runner/agent_pipeline.py` may (009). `agents/control.py` reaches citations only through its `CitationCheck` protocol, never `logbooks`.
- `telemetry` imports only `domain`. `runner/agent_pipeline.py` may import `agents`, `mcp_server`, `telemetry`, `logbooks` and `config`, never `anthropic` (the model is injected).
- `logbooks` imports only `domain`, `ingestion` and `logbooks`, and loads files only through `read_logbook_texts`. `mcp_server` imports only `domain`, `metrics`, `cases`, `logbooks`, `mcp_server` and `mcp`; never `config`, `runner`, `agents`, `evaluation` or `anthropic`, and from `cases` never `cases.draft`, `cases.ledger` or `cases.registry.causes_repo` (it knows only the writer protocols in `mcp_server/context.py`, 008 R21).
- `evaluation` imports only `domain` and `ingestion`, with one exception: `evaluation/sources.py` imports `read_deliverables` from `cases.registry.notices` (ADR-0011). It never imports `cases.novelty`, so noise is judged independently of the code under test.
- `evals/` holds thin scripts: they read `get_settings()`, call `evaluation` or `runner`, and turn errors into one line and an exit code. No logic lives there.

## Design patterns

| Pattern | Where | Why |
|---|---|---|
| State machine (pure transition function) | `cases/lifecycle.py` | Every transition lives in one `next_state` table, tested row by row; four states don't justify a class per state. |
| Strategy | `metrics/severity.py` | Delay thresholds differ per market (Local has `media`; Brazil and Europe do not). |
| Repository | `cases/registry/` | The tracker depends on the small `CaseRepository` protocol; tests use SQLite `:memory:`, not a second in-memory implementation. |
| Pipeline | `runner/` | ingest → metrics → lifecycle → agent → notify, each step pure where possible. |
| Chain of Responsibility | `hooks/` | Guards run in order, and the first to block returns its reason. |
| Factory | `agents/factory.py` | Builds each agent with its prompt and its tool allowlist. |
| Ports and Adapters | `notify/` | The output channel is pluggable without touching the core. |
| Composite | `notify/composite.py` | Console and file channels behind one `Notifier`; only durable, idempotent channels may raise. |
| Transactional outbox | `cases/registry/notices.py`, `runner/outbox.py` | Notices are stored in the snapshot's transaction and delivered after commit, so none is lost or sent early (ADR-0010). |

## Tests vs evals
- **Tests** (`tests/`) check code against rules and run in CI with no network.
- **Evals** (`evals/`) check system behavior, including the model, against golden cases. They run on demand on real data (days 1–7 only) and cost money once the agent is in the loop. The evaluator code itself (`src/plant_monitor/evaluation/`) is tested in CI like any module, with synthetic fixtures.
