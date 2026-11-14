# US-09 · Guardrails block invalid notices

**As a** developer, **I want** code-level hooks and per-agent permissions that stop invalid actions, **so that** the rules hold even when the model gets them wrong.

**Requirements:** FR-15, FR-31, FR-32

> Reinterpreted in spec 010 (D9). Since spec 007 code decides every notice, its severity and the news set, and the model writes only `texto`. So the scenarios target what the model can actually do: emit texts for cases, state severities in a text, and end its turn.

## Acceptance criteria
```gherkin
Feature: Hooks and permissions

  Scenario: Repeated notice without news is blocked
    Given a case was reported at "alta" in "en_seguimiento" and has not changed since
    When the agent emits a text for it
    Then the hook blocks the call with reason "<case_id>: no news since last report"
    And the model receives the reason as a tool error

  Scenario: A text stating a severity below the notice's is blocked
    Given a notice whose severity is "alta"
    When the agent writes a texto stating "severidad media"
    Then the hook blocks it with reason "texto for <case_id> states severidad media: below notice severity (alta)"

  Scenario: Incomplete shift report is blocked
    Given 3 news items at a closing snapshot
    When the agent submits texts for 2 of them and ends its turn
    Then the stop hook blocks the end of turn naming the notices still missing

  Scenario: Read-only agents cannot write
    Given the investigator, whose allowlist has no write tools
    When it attempts a write tool such as "apply_proposal", "emit_alert" or "set_cause"
    Then the call is rejected by code before reaching the MCP server
    And the block is recorded in the trace's hooks
```
