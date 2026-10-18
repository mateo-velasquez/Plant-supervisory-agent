# Case state machine (§3)

```mermaid
stateDiagram-v2
    [*] --> abierto: deviation and no active case
    abierto --> en_seguimiento: next snapshot
    abierto --> escalado: critica (threshold or agent)
    en_seguimiento --> escalado: critica (threshold or agent)
    en_seguimiento --> resuelto: 2 clean snapshots, no agent raise in force
    escalado --> resuelto: 2 clean snapshots, no agent raise in force
    resuelto --> [*]

    note right of escalado
        Sticky: stays escalado even if severity drops.
        Entering escalado emits exactly one alerta_inmediata.
    end note
    note left of resuelto
        A later deviation opens a NEW case.
    end note
```

## Rules not visible in the diagram
- At most one active case (`abierto`, `en_seguimiento` or `escalado`) per combination.
- For novelty, `abierto` and `en_seguimiento` count as the same state.
- Severity never goes below the computed minimum. The agent may only raise it.
- Whether `abierto` can resolve directly is not stated in §3; we assume it cannot, because it moves to `en_seguimiento` first.
- A case that opens already at `critica` opens and escalates in the same snapshot, and its alert fires there (Q-08 in the requirements).
