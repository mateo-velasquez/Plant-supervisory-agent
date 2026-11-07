# Case state machine (§3)

```mermaid
stateDiagram-v2
    [*] --> abierto: deviation and no active case
    [*] --> escalado: deviation at critica (threshold or raise in force; Q-08, §5)
    abierto --> en_seguimiento: next snapshot
    abierto --> escalado: critica (threshold or agent)
    en_seguimiento --> escalado: critica (threshold or agent)
    en_seguimiento --> resuelto: ≥ 2 consecutive clean snapshots, no agent raise in force
    escalado --> resuelto: ≥ 2 consecutive clean snapshots, no agent raise in force
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
- `abierto` never resolves directly: the opening snapshot always has a deviation, so the clean streak is at most 1 when the case leaves `abierto`.
- A case that opens already at `critica`, by threshold or by a raise in force, opens and escalates in the same snapshot, and its alert fires there (Q-08 in the requirements).
- Clean snapshots count toward the streak while a raise is in force; resolution needs a streak of at least `resolucion.snapshots_sin_desvio` (2) and no raise in force at that snapshot, so a lift can resolve a case with a longer streak (Q-25).
- Current severity is the snapshot's effective severity, even `ninguna`; the max since the last report keeps the peak (Q-26).
- The max since the last report excludes the report snapshot: marking a case reported empties it, and the next snapshot sets it (Q-28).
- A raise or lift decided by the agent at a snapshot takes effect at that same snapshot: the tracker re-evaluates it from the pre-snapshot state (Q-27).
- Transitions are one pure function, `next_state` in `cases/lifecycle.py`.
