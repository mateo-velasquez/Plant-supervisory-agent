# 0014 · Coordinator loop contract: template fallback, notice draft writer, budget guard and sync-to-async bridge

- **Status:** Accepted
- **Date:** 2026-11-08
- **Requirements:** FR-22, FR-25, FR-29, FR-37, FR-38, NFR-02, NFR-07, NFR-09, NFR-10 (Q-41–Q-45)

## Context
Spec 007 puts the coordinator in the loop: for each snapshot with a deliverable text, the model writes the `texto` of the alerts and report news that code already decided (ADR-0002). The loop is our own (ADR-0007) and reaches the data through the in-process `ToolClient` (ADR-0013). Four forces shape it:
- The series runs unattended and the held-out days run once (ADR-0008), so a model failure must not lose a snapshot's notices or block the series.
- No request may exceed 100k prompt tokens (NFR-02). Above that, Haiku 5.5 bills every token at 5× (D3, checked 2026-11-08), and `count_tokens` is an estimate.
- Write tools must write inside the runner's open unit of work, on its thread and connection (ADR-0003, ADR-0013). Notices are saved once per snapshot and never edited with `model_copy` (ADR-0010, spec 004 Q-27 note).
- The runner's `SnapshotPipeline.process` is synchronous, while `ToolClient` and the SDK client are async.

## Decision
- **When to call (Q-41):** the model is called only when the snapshot has a deliverable text: an alert, or a news item in a closing report. Otherwise code saves the template notices and nothing is sent.
- **Notice draft and writer:** the write tools (`emit_alert`, `emit_shift_report`) fill `texto` into an in-memory draft of the snapshot's notices, through a narrow writer protocol carried by the snapshot frame. When the loop ends, the notices are rebuilt through their validators and saved exactly once.
- **Template fallback (Q-43):** if the budget would be exceeded, the turn cap is reached, the model refuses, hits `max_tokens` or stops unexpectedly, or texts are still missing after one reminder, those texts keep the template and the snapshot commits. API errors that persist after our own retries (`max_retries=0` on the SDK client, exponential backoff with jitter), and non-retryable errors, raise and the run stops with `RunAborted`, resumable at that snapshot.
- **Budget guard:** before every request the loop counts its tokens. Above `prompt_token_limit` (default 95,000, at most 100,000; the margin covers the estimate) the request is not sent.
- **Sync-to-async bridge:** `AgentPipeline.process` runs the loop with `anyio.run` on the runner's thread, so the async tool wrappers share the registry connection. The SDK client lives inside each snapshot's event loop.
- **Trace (Q-44):** one JSON-lines file per run. A committed snapshot's line is staged and appended after commit; an aborted snapshot's line is appended at once, because its tokens were spent.

## Alternatives considered
- **Abort on every model failure:** keeps "every text is the agent's", but one refusal or a long prompt would stop the unattended series and the single held-out run.
- **Skip the notice on failure:** an alert without text is worse than one with the template text; silence would also break §4.
- **SDK built-in retries:** less code, but its backoff is hard to assert without a network, and the own loop already owns retries (ADR-0007).
- **Tools write notices directly to the registry:** a later tool in the same loop would see half-written rows, and 008's re-`track` (Q-27) needs one final build.
- **Run the loop in a worker thread or with `check_same_thread=False`:** a second thread would touch the open transaction, against ADR-0003.
- **Trace rows in the registry (schema v3):** transactional, but a schema change for observability data; revisit in spec 013 if the demo needs queries.

## Consequences
- Positive: a model failure never loses a snapshot's notices or stops the series; cost stays at the base rate; the whole loop is testable with a fake model and a fake tool port (NFR-07); every snapshot has a trace line, aborted ones included (FR-37, FR-38).
- Negative / risks: a fallback notice carries template text, so text quality depends on the fallback rate, which the trace must make visible. The 5% budget margin can block a request that would have fit. Exceptions raised inside `ToolClient` arrive wrapped in an exception group and must be unwrapped at the `anyio.run` boundary.
- Follow-ups:
  - Spec 008 adds `set_cause`, `raise_severity` and `lift_severity_raise` writers on the same draft, with a runner-side adapter that re-runs `track` (Q-27).
  - Spec 010 adds hooks around the same tool calls; the trace's `hooks` field is filled there.
  - Spec 011 adds prompt caching on the stable prefix (tools, system prompt v1).
