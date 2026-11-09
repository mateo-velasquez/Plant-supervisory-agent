# 0015 · Closing-snapshot review trigger, active-cause ledger and runner-side judgment adapter

- **Status:** Accepted
- **Date:** 2026-11-08
- **Requirements:** FR-15–FR-19, FR-29, FR-37, FR-38, NFR-10 (Q-02, Q-11, Q-29, Q-30, Q-41 amended, Q-47–Q-49)

## Context
Spec 008 lets the coordinator cite causes and apply §5 raises. Three forces shape the design:
- Spec 007 calls the model only when a snapshot has a deliverable text (Q-41). The Europe audit (Q-39) shows the gap: T07 becomes readable at S014, where no case exists and the report is empty, so nobody reads it. The case then opens at the mid snapshot S015 with no alert, so the raise and its S015 alert never happen.
- A raise must reach every active case with that cause, and cases opened while it is in force (§5). It must survive across snapshots and runs, outside the model (ADR-0002, ADR-0003), and code, not the model, must decide which cases it reaches (Q-02).
- A raise or lift decided at N must escalate or resolve at N (Q-27). That re-runs `track` inside the open unit of work. Notices are rebuilt through their validators and saved once per snapshot (ADR-0010, ADR-0014). Write tools write through narrow writers on the runner's thread (ADR-0013).

## Decision
- **Trigger:** the coordinator is called at every closing snapshot (`decision_reason = closing_review` when no text is due) and, as before, at any snapshot with a deliverable text. A bottleneck without a cause is not a trigger.
- **Active-cause ledger:** an active cause (category, stage, scope `modelo` + `etapa` + optional `mercado`, opening and lifting citations) is a registry entity (schema v3, migrated in place from v2). `CauseLedger` in `cases/ledger.py` holds the rules. Code links cases to it: at the raise, at opening, and at every later snapshot while it is in force (Q-49). Links are sticky. The raise gives its cause to linked cases that have no cited cause (Q-48), and a lift undoes only the severity effect (Q-30).
- **Runner-side adapter:** `SnapshotJudgment` in `runner/judgment.py` implements the frame's writer protocols. Each judgment write calls the ledger, then `redecide` (re-runs `track` with the current raises, Q-27), then rebases the notice draft. A failure that is not a refusal is stored, closes every later write, and is raised after the loop and before `finish`, so the snapshot rolls back and can be resumed.

## Alternatives considered
- **Call the model only when there is a deliverable text (007 as is):** cheapest, but a §5 raise readable at a closing with no news is lost (Q-39).
- **Call the model at every snapshot:** mid snapshots never bring a new logbook, so no new judgment is possible there. It would double the calls for nothing.
- **The model lists the cases a raise reaches:** fewer rules in code, but scope would be model output, untestable and against ADR-0002.
- **Raises stored as flags on cases:** cannot cover cases that open later, or a raise recorded when no case exists (Q-39).
- **Tools write the registry directly, with no adapter:** the re-`track` and the single save would be scattered across tools, and a later tool would see half-built notices (ADR-0014).

## Consequences
- Positive:
  - §5 works end to end, including raises recorded with no case.
  - Scope, linking and resolution blocking are deterministic and unit-tested.
  - The registry keeps each raise's citations for the trace (FR-38).
  - An internal tool failure aborts cleanly, with no half-written rows.
- Negative / risks:
  - About 21 extra calls over days 1–7, mostly at closings with no text. Cost is measured by `evals/agent_days_1_7.py`.
  - Schema v3 needs a migration.
  - A text written before a later judgment write can be reset to pending.
- Follow-ups:
  - Spec 010's hooks wrap the new tools.
  - Spec 011 caches the larger prompt v2 prefix.
  - The verified-evidence type from `LogbookStore` is deferred.
