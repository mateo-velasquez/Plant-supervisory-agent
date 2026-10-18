# US-10 · Trace any alert back to its evidence

**As a** plant manager, **I want** to see for any alert in which snapshot it fired, why, and with which quote, **so that** I can audit the system's decisions.

**Requirements:** FR-25, FR-38

## Acceptance criteria
```gherkin
Feature: Alert trace

  Scenario: Reconstruct an alert
    Given an alert emitted at S020 for Pickup × Local
    When I request its trace
    Then I see the metrics at S020 (gap, delay, minimum severity, bottleneck)
    And the state transition that triggered it
    And the logbook citations used
    And the agent tool calls and hook decisions involved
```
