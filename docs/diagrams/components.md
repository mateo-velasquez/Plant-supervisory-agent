# Components

```mermaid
flowchart TB
    runner[Series runner<br/>llegadas.csv order]

    subgraph core[Deterministic core · code]
        ingest[Ingestion<br/>schemas, BOM, dedupe]
        metrics[Metrics engine<br/>gap · delay · bottleneck · min severity]
        lifecycle[Case lifecycle<br/>state machine]
        novelty[Novelty rules<br/>what is news]
        registry[(Case registry<br/>SQLite v4: cases, causes, active causes, logbook reviews)]
        ledger[Cause ledger<br/>scope matching · links · raises]
        logstore[Logbook store<br/>availability · missing · citation check]
        persp[Perspectives<br/>gap · shipment · bottleneck]
        notify[Notifier port<br/>console · file]
    end

    subgraph steps[Agent steps · runner]
        review[Investigator step<br/>pending logbooks · review marks]
        control[Control · code<br/>schema · size · estado_causa · verify_citation]
        coordstep[Coordinator step<br/>brief v3 · proposal book]
        adapter[Judgment adapter<br/>ledger → redecide → draft rebase]
    end

    subgraph mcp[Own MCP server · two servers, one frame holder]
        invtools[Investigator server<br/>list_available_logbooks · get_logbook · get_case · get_delayed_units]
        coordtools[Coordinator server<br/>get_deviations · get_active_cases · get_case · get_delayed_units<br/>apply_proposal · emit_alert · emit_shift_report]
        prompt[Criteria prompt · 010]
    end

    subgraph agents[Agent layer · Anthropic API]
        investigator[Cause investigator<br/>read-only, the only reader of logbooks]
        coordinator[Coordinator<br/>single writer, never reads logbooks]
    end

    hooks{{Hooks + tool allowlists · 010<br/>pre-tool · post-tool · on-stop}}

    runner --> ingest --> metrics --> lifecycle --> registry
    lifecycle --> novelty
    ledger -- raises in force --> lifecycle
    ledger --> registry
    runner -- unreviewed logbook --> review --> investigator
    investigator -- tool calls --> hooks --> invtools
    investigator -- proposals JSON --> control
    control -. verify_citation .-> logstore
    control -- validated proposals --> coordstep
    persp --> coordstep
    coordstep -- brief --> coordinator
    coordinator -- tool calls --> hooks --> coordtools
    invtools --> registry & logstore & metrics
    coordtools --> registry & metrics
    coordtools -- apply_proposal · emit_* --> adapter
    coordtools -. verify_citation · apply_proposal .-> logstore
    adapter --> ledger & lifecycle
    review -- marks after the coordinator --> registry
    prompt -. system context .-> coordinator
    registry -- outbox after commit --> notify
    hooks -. checks .-> novelty
    hooks -. checks .-> registry
```

## Responsibilities
- **Deterministic core:** computes everything that is arithmetic or an explicit rule, including the gap, shipment and bottleneck perspectives of the coordinator brief (Q-50). It never calls the model.
- **MCP server:** the only door between agents and data. Each agent gets its own server with only its tools; both share one frame holder on the runner's thread (ADR-0009, ADR-0013).
- **Cause investigator:** the only agent that reads logbooks. It runs when a readable logbook is neither reviewed nor given up (Q-51, Q-52), has no write tool and returns typed proposals with citations.
- **Control:** code checks each proposal (schema, size, `estado_causa` against the type, verbatim and readable citation), with one correction round and a safe fallback.
- **Coordinator:** the single writer. It never reads a raw logbook; it applies validated proposals by id (`apply_proposal`) and writes the texts. It runs only with a text to write or a validated proposal (Q-51).
- **Cause ledger and judgment adapter:** code links cases to an active cause by scope (Q-02, Q-49) and feeds the raises to the lifecycle. Each judgment write re-runs `track` (Q-27) and rebuilds the notices; they are saved once per snapshot (ADR-0015).
- **Hooks (spec 010):** code around every tool call. They enforce the allowlists, the severity floor, no repeats without news and report completeness, returning violations to the model as tool errors.
