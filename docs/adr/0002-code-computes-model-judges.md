# 0002 · Code computes and enforces; the model judges and writes

- **Status:** Accepted
- **Date:** 2026-10-18
- **Requirements:** FR-05–FR-15, FR-16–FR-24, FR-31

## Context
The brief fixes that metrics (gap, delay, minimum severity, bottleneck) are code. It leaves open whether the **case lifecycle** and **what counts as news** are applied by code or by the agent. The model is Claude Haiku 5.5: fast and cheap, so the design must cover what the model cannot do reliably on its own. The hardest notice is `sin_aviso` (staying silent), and repeated or missing news counts as error.

## Decision
- **Code** computes the metrics, applies the threshold-driven lifecycle (open, follow-up, escalate by threshold, resolve) and computes **which cases are news** at each shift close.
- **The agent** reads logbooks and decides the cause with its citation, decides whether a logbook justifies raising severity, and writes the text of alerts and reports.
- **Hooks** enforce the agreement: any agent action that contradicts the code's computation is blocked with a reason. Examples are a notice below the floor, news that is not news, or a report missing an active case.

## Alternatives considered
- **Agent applies the lifecycle and novelty:** more "agentic", but non-deterministic. Errors in the most costly area (silence) would depend on the model, and they would be hard to test.
- **Code does everything, including causes:** cause extraction from free text is the genuine judgment task, and keyword rules would not generalize to unseen logbooks (days 8–10).

## Consequences
- Positive: threshold-driven behavior is deterministic and unit-testable, and noise is prevented by construction. Model calls only happen when there is a delta or a shift close, which lowers cost.
- Negative: the agent has less freedom; agent-driven escalations must flow back into the code lifecycle through a write tool (`raise_severity`).
- Follow-up: the W2 spec defines how a logbook cause links to cases (Q-02).
