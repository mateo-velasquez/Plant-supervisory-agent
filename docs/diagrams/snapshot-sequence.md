# Processing one snapshot

```mermaid
sequenceDiagram
    autonumber
    participant R as Runner
    participant I as Ingestion
    participant P as ThresholdPipeline
    participant M as Metrics engine
    participant L as Case tracker
    participant N as Novelty + notice builder
    participant DB as Registry
    participant C as Coordinator agent
    participant H as Hooks
    participant S as MCP server
    participant O as Outbox dispatcher
    participant Ch as Notifiers

    R->>O: flush pending (run start, ADR-0010)
    O->>Ch: deliver leftovers from an earlier run
    R->>DB: already processed(snapshot_id)?
    alt duplicate
        DB-->>R: yes
        R->>R: log skip, continue
    else new
        R->>I: load + validate snapshot
        I-->>R: Snapshot
        R->>DB: processing(commit): BEGIN
        R->>P: process(snapshot, shift, position)
        P->>DB: released so far
        P->>M: compute(snapshot, released, plant context)
        M-->>P: metrics per combination
        P->>DB: record releases
        P->>L: track(metrics, raises)
        L->>DB: open / transition cases (threshold-driven)
        L-->>P: delta (the last one wins, Q-27)
        opt delta is not empty (spec 007 onward)
            P->>C: delta + snapshot context (system: role + criteria prompt)
            loop until done
                C->>H: pre-tool: tool call
                H->>H: allowlist, novelty, text floor, cause (against the decision view)
                alt allowed
                    H->>S: forward
                    S-->>C: result
                    C->>H: post-tool: floor check after apply_proposal
                    H-->>R: violation = code bug, abort snapshot (resumable)
                else blocked
                    H-->>C: tool error with reason (recorded in trace hooks)
                end
            end
            C->>H: on-stop: completeness
            H-->>C: note naming missing texts, or end of turn
        end
        P->>N: build decisions from the last delta (+ report at closing, see shift-close)
        N-->>P: alerts, per-case decisions, report
        P->>DB: save notices (outbox rows)
        opt closing snapshot
            P->>DB: mark reported cases
        end
        R->>DB: mark processed + COMMIT (same transaction)
        R->>O: after commit
        O->>DB: pending deliverable rows (seq order)
        O->>Ch: alert / report
        O->>DB: mark delivered
    end
```

## Notes
- Threshold-driven transitions happen in code before the agent runs, so the agent starts from the true state.
- If the delta is empty and it is not a closing snapshot, no model call is made. Silence costs nothing. Until spec 007 the pipeline runs without the agent.
- Notices are stored inside the snapshot's transaction and delivered only after the commit (ADR-0010). A crash after the commit leaves them pending, and the next run delivers them first. A notice can be resent only if the process dies between a send and its delivered mark.
- Marking the snapshot as processed is atomic with its writes, which makes reruns safe (FR-02, NFR-10).
- The investigator goes through the same loop with the allowlist hook only. Hooks read the code's decision through `DecisionView` and never recompute a rule. Repeated blocks end in the turn cap fallback (spec 010, ADR-0016).
