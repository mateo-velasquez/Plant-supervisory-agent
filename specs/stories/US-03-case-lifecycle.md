# US-03 · Track one case per deviation

**As a** production control analyst, **I want** each deviation tracked as a single case with a clear state, **so that** I follow one story per problem instead of a pile of repeated warnings.

**Requirements:** FR-12, FR-13, FR-14, FR-15 · State machine: [diagram](../../docs/diagrams/case-state-machine.md)

## Acceptance criteria
```gherkin
Feature: Case lifecycle

  Scenario: A deviation opens a case
    Given Pickup × Brasil has no active case
    When its minimum severity becomes "media"
    Then a case opens in state "abierto"

  Scenario: The next snapshot moves it to follow-up
    Given a case opened in the previous snapshot
    When the next snapshot still shows a deviation
    Then the case is "en_seguimiento"

  Scenario: Only one active case per combination
    Given Pickup × Brasil has an active case
    When a new deviation is computed for Pickup × Brasil
    Then no second case is opened

  Scenario: Escalation is sticky
    Given a case reached "critica" and is "escalado"
    When its severity drops to "alta"
    Then the case remains "escalado"

  Scenario: Resolution needs two clean snapshots
    Given an active case with no agent escalation in force
    When the combination has no deviation for 2 consecutive snapshots
    Then the case is "resuelto"

  Scenario: An agent escalation in force blocks resolution
    Given an active case raised by the agent and the cause is still ongoing
    When the combination has no deviation for 2 consecutive snapshots
    Then the case is not resolved

  Scenario: A new deviation after resolution is a new case
    Given the case for Pickup × Brasil was resolved
    When Pickup × Brasil deviates again
    Then a new case with a new ID opens
```
