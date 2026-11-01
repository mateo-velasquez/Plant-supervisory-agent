# 013 · Alert trace for the demo — Spec

- **Status:** Draft
- **Requirements:** FR-25, FR-38
- **Stories:** US-10
- **Week:** W7

## Goal
For any alert, show in which snapshot it fired, why and with which quote, rebuilt from the registry and the trace log. This is the centerpiece of the Demo Day.

## Scope
- In: trace query; `plant-monitor trace <notice_id>` command; choice of the demo alert; demo script and fallback.
- Out: any new behavior of the system.

## Behavior
- Given a notice, the trace shows: the metrics at its snapshot (gap, delay, minimum severity, bottleneck), the state transition that triggered it, the logbook citations used, and the agent tool calls and hook decisions involved (US-10, FR-38).
- The trace is rebuilt only from stored data (registry plus trace log), never by rerunning the model.

## Worked examples
To be written when the spec moves to Ready. Candidate demo alerts: the Europe audit (EUR-0305 missed, T07 → T10) or the Pickup stop raised by the agent (T17 → T19).

## Edge cases and assumptions
- A threshold-only alert has no tool calls; the trace says so explicitly.

## Acceptance
- [ ] The trace command has passing tests on a synthetic run.
- [ ] The demo script is rehearsed once end to end, with a recorded fallback run.
