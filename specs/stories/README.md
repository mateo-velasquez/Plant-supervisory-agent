# User stories

Each story is one file `US-NN-short-name.md` with: persona, story, linked requirements and Gherkin acceptance criteria. Acceptance criteria are the seed for tests and evaluator cases.

## Personas
- **Production control analyst**: monitors the plant every few hours and decides what to escalate. Today does this job by hand.
- **Plant manager**: receives immediate alerts and reads shift reports. Wants signal, not noise.
- **Developer**: builds and evolves the system; needs guardrails, traces and an evaluator.

## Index

| ID | Story | Requirements | Week |
|---|---|---|---|
| [US-01](US-01-process-series.md) | Process the series once per snapshot | FR-01–FR-04 | W1 |
| [US-02](US-02-deviation-metrics.md) | Know each combination's deviation | FR-05–FR-11 | W1 |
| [US-03](US-03-case-lifecycle.md) | Track one case per deviation | FR-12–FR-15 | W1 |
| [US-04](US-04-immediate-alert.md) | Get one alert when a case escalates | FR-21, FR-25 | W1 |
| [US-05](US-05-shift-report.md) | Read a shift report with only what changed | FR-22–FR-24 | W1 |
| [US-06](US-06-cited-cause.md) | See the cause with its citation | FR-16–FR-18 | W2 |
| [US-07](US-07-logbook-escalation.md) | Escalate when a cause has no end date | FR-19 | W2 |
| [US-08](US-08-logbook-injection.md) | Logbooks cannot instruct the agent | FR-20 | W3 |
| [US-09](US-09-guardrails.md) | Guardrails block invalid notices | FR-15, FR-31, FR-32 | W4 |
| [US-10](US-10-alert-trace.md) | Trace any alert back to its evidence | FR-25, FR-38 | W1 / W7 |
| [US-11](US-11-unattended-run.md) | Run the full series unattended, with cost | FR-33, FR-36, FR-37 | W4 / W6 |
| [US-12](US-12-evaluator.md) | Know if a change improved or broke the system | FR-39, FR-40 | W1 → W5 |

Examples use synthetic numbers unless they quote a logbook from days 1–7. Days 8–10 are never used in stories.
