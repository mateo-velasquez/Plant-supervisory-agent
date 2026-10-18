# Processing one snapshot

```mermaid
sequenceDiagram
    autonumber
    participant R as Runner
    participant I as Ingestion
    participant M as Metrics engine
    participant L as Case lifecycle
    participant DB as Registry
    participant C as Coordinator agent
    participant H as Hooks
    participant S as MCP server

    R->>DB: already processed(snapshot_id)?
    alt duplicate
        DB-->>R: yes
        R->>R: log skip, continue
    else new
        R->>I: load + validate snapshot
        I-->>R: Snapshot
        R->>M: compute(snapshot, plan, standards, shipments)
        M-->>R: metrics per combination
        R->>L: apply thresholds(metrics, active cases)
        L->>DB: open / transition cases (threshold-driven)
        L-->>R: delta (what changed)
        opt delta is not empty
            R->>C: delta + snapshot context
            loop until done
                C->>H: tool call
                H->>H: allowlist, floor, novelty checks
                alt allowed
                    H->>S: forward
                    S-->>C: result
                else blocked
                    H-->>C: tool error with reason
                end
            end
        end
        opt closing snapshot of a shift
            R->>C: build shift report (see shift-close)
        end
        R->>DB: mark processed (same transaction)
    end
```

## Notes
- Threshold-driven transitions happen in code before the agent runs, so the agent starts from the true state.
- If the delta is empty and it is not a closing snapshot, no model call is made. Silence costs nothing.
- Marking the snapshot as processed is atomic with its writes, which makes reruns safe (FR-02, NFR-10).
