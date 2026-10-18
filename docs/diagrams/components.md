# Components

```mermaid
flowchart TB
    runner[Series runner<br/>llegadas.csv order]

    subgraph core[Deterministic core · code]
        ingest[Ingestion<br/>schemas, BOM, dedupe]
        metrics[Metrics engine<br/>gap · delay · bottleneck · min severity]
        lifecycle[Case lifecycle<br/>state machine]
        novelty[Novelty rules<br/>what is news]
        registry[(Case registry<br/>SQLite)]
        logstore[Logbook store<br/>availability + citation check]
        notify[Notifier port<br/>console · file]
    end

    subgraph mcp[Own MCP server]
        readtools[Read tools<br/>deviations, cases, logbooks]
        writetools[Write tools<br/>set_cause · raise_severity<br/>emit_alert · emit_shift_report]
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

    runner --> ingest --> metrics --> lifecycle --> registry
    lifecycle --> novelty
    runner -- delta --> coordinator
    coordinator --> gap & ship & bottle & cause
    coordinator -- tool calls --> hooks
    gap & ship & bottle & cause -- tool calls --> hooks
    hooks --> readtools & writetools
    prompt -. system context .-> coordinator
    readtools --> registry & logstore & metrics
    writetools --> registry
    writetools --> notify
    hooks -. checks .-> novelty
    hooks -. checks .-> registry
```

## Responsibilities
- **Deterministic core:** computes everything that is arithmetic or an explicit rule. It never calls the model.
- **MCP server:** the only door between agents and data. Tools return compact, filtered views, never full datasets.
- **Coordinator:** the only agent whose allowlist includes write tools. It decides cause, escalation and wording.
- **Analysts:** read-only specialists, introduced in W3. In W1 the coordinator works alone.
- **Hooks:** code that runs around every tool call. They enforce the severity floor, block repeats without news and check report completeness, returning violations to the model as tool errors.
