# US-06 · See the cause with its citation

**As a** plant manager, **I want** every case's cause quoted from the logbook it came from, **so that** I can trust it and check it myself.

**Requirements:** FR-16, FR-17, FR-18

## Acceptance criteria
```gherkin
Feature: Cited cause

  Scenario: Cause taken from the logbook
    Given an active case for SUV × Europa with bottleneck "calidad"
    And logbook T07 says "retuvo en calidad las SUV de exportación"
    When the cause is assigned
    Then categoria is "retencion_de_calidad" and etapa is "calidad"
    And evidencia cites bitacora "T07" with that fragment

  Scenario: The citation must exist verbatim
    Given the agent cites a fragment that is not in the cited logbook
    When the cause is submitted
    Then it is rejected with the reason "fragment not found in T07"

  Scenario: No logbook explains it
    Given an active case with bottleneck "pintura"
    And no available logbook names a cause for it
    Then categoria is "no_declarada" and etapa is "pintura"
    And evidencia is empty

  Scenario: Unrelated logbook content is not a cause
    Given a logbook that only reports a safety talk and full staffing
    Then no cause is derived from it
```
