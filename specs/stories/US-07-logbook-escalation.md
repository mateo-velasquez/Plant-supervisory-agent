# US-07 · Escalate when a cause has no end date

**As a** plant manager, **I want** a case escalated when the logbook says its cause is ongoing with no resolution date, even before thresholds trip, **so that** I hear about open-ended problems early.

**Requirements:** FR-19, FR-15

## Acceptance criteria
```gherkin
Feature: Escalation from logbook

  Scenario: Ongoing cause without date escalates
    Given an active case for Pickup × Local with bottleneck "montaje"
    And logbook T17 says "no hay fecha confirmada de vuelta"
    When the agent reviews the case
    Then severity is raised to "critica" with origen "agente"
    And the raise cites T17 with that fragment

  Scenario: The raise applies to every case with that cause
    Given the Pickup assembly stop is in force
    When a Pickup × Brasil case opens while it is still in force
    Then that case is also raised to "critica"

  Scenario: A later logbook ends the raise
    Given the raise from T17 is in force
    And logbook T19 says "la línea de montaje de Pickup volvió a las 10:00"
    Then the raise is no longer in force
    And the minimum severity applies again

  Scenario: A concrete date does not escalate
    Given a logbook says a supplier delivers "el jueves a las 8:00"
    Then severity is not raised; thresholds suffice

  Scenario: An already resolved problem does not escalate
    Given logbook T10 says the audit "terminó a las 8:30"
    Then severity is not raised
```
