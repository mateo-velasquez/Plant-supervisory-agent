# US-09 · Guardrails block invalid notices

**As a** developer, **I want** code-level hooks and per-agent permissions that stop invalid actions, **so that** the rules hold even when the model gets them wrong.

**Requirements:** FR-15, FR-31, FR-32

## Acceptance criteria
```gherkin
Feature: Hooks and permissions

  Scenario: Repeated notice without news is blocked
    Given a case was reported at "alta" in "en_seguimiento"
    When the agent tries to report it again with no change
    Then the hook blocks the call with reason "no news since last report"
    And the model receives the reason as a tool error

  Scenario: Severity below the floor is blocked
    Given the computed minimum severity is "alta"
    When the agent emits a notice with severity "media"
    Then the hook blocks it with reason "below minimum severity (alta)"

  Scenario: Incomplete shift report is blocked
    Given 3 active cases at closing
    When the agent submits a report listing 2
    Then the stop hook blocks it naming the missing case

  Scenario: Read-only agents cannot write
    Given an analyst agent without write tools in its allowlist
    When it attempts a registry write tool
    Then the call is rejected by code before reaching the MCP server
```
