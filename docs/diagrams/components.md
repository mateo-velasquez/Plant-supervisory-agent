# Components

```mermaid
flowchart TB
    runner[Series runner<br/>llegadas.csv order]

    subgraph core[Deterministic core · code]
        ingest[Ingestion<br/>schemas, BOM, dedupe]
        metrics[Metrics engine<br/>gap · delay · bottleneck · min severity]
        lifecycle[Case lifecycle<br/>state machine]
        novelty[Novelty rules<br/>what is news]
        registry[(Case registry<br/>SQLite v3: cases, causes, active causes)]
        ledger[Cause ledger<br/>scope matching · links · raises]
        logstore[Logbook store<br/>availability + citation check]
        notify[Notifier port<br/>console · file]
    end

    subgraph mcp[Own MCP server]
        readtools[Read tools<br/>deviations, cases, logbooks]
        writetools[Write tools<br/>set_cause · raise_severity · lift_severity_raise<br/>emit_alert · emit_shift_report]
        prompt[Criteria prompt]
    end

    subgraph agents[Agent layer · Anthropic API]
        coordinator[Coordinator<br/>single writer]
        gap[Gap analyst<br/>read-only]
        ship[Shipment-risk analyst<br/>read-only]
        bottle[Bottleneck analyst<br/>read-only]
        cause[Cause investigator<br/>read-only, logbooks]
    end

    hooks{{Hooks + tool allowlists<br/>pre-tool · post-tool · on-stop}}
    adapter[Judgment adapter · runner<br/>ledger → redecide → draft rebase]

    runner --> ingest --> metrics --> lifecycle --> registry
    lifecycle --> novelty
    ledger -- raises in force --> lifecycle
    ledger --> registry
    runner -- delta --> coordinator
    coordinator --> gap & ship & bottle & cause
    coordinator -- tool calls --> hooks
    gap & ship & bottle & cause -- tool calls --> hooks
    hooks --> readtools & writetools
    prompt -. system context .-> coordinator
    readtools --> registry & logstore & metrics
    writetools -- writer protocols --> adapter
    adapter --> ledger & lifecycle
    writetools -. verify_citation .-> logstore
    registry -- outbox after commit --> notify
    hooks -. checks .-> novelty
    hooks -. checks .-> registry
```

## Responsibilities
- **Deterministic core:** computes everything that is arithmetic or an explicit rule. It never calls the model.
- **MCP server:** the only door between agents and data. Tools return compact, filtered views, never full datasets.
- **Coordinator:** the only agent whose allowlist includes write tools. It decides cause, escalation and wording. It runs at every closing snapshot and at any snapshot with a text to write (ADR-0015).
- **Cause ledger and judgment adapter:** code links cases to an active cause by scope (model + stage, market if named; Q-02, Q-49) and feeds the raises to the lifecycle. Each judgment write re-runs `track` (Q-27) and rebuilds the notices; they are saved once per snapshot (ADR-0015).
- **Analysts:** read-only specialists, introduced in W3. In W1 the coordinator works alone.
- **Hooks:** code that runs around every tool call. They enforce the severity floor, block repeats without news and check report completeness, returning violations to the model as tool errors.
