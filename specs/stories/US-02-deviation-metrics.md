# US-02 · Know each combination's deviation

**As a** production control analyst, **I want** the gap, delay, bottleneck stage and minimum severity of every model × market computed the same way every time, **so that** decisions start from correct, reproducible numbers.

**Requirements:** FR-05 to FR-11 · Detailed in [spec 001](../001-deviation-metrics/spec.md)

## Acceptance criteria
```gherkin
Feature: Deviation metrics

  Scenario: Gap at mid-shift
    Given Sedán × Local plans 12 units for T01
    And 2 distinct Sedán × Local units were released by the mid snapshot
    When metrics are computed at the mid snapshot
    Then the cumulative plan is 6
    And the gap is -4 units, -11.1% of the daily plan (36)
    And the gap severity is "media"

  Scenario: Small gaps are not deviations
    Given a combination is 2 units behind plan
    When metrics are computed
    Then it has no gap severity, whatever the percentage

  Scenario: A unit released twice counts once
    Given unit U001 appears in "liberadas" of two snapshots
    When progress is computed
    Then U001 is counted once

  Scenario: Missing the Europe ship costs a week
    Given an SUV × Europa unit assigned to EUR-0305
    And its projected yard arrival is after the EUR-0305 yard cut-off
    When delay is computed
    Then the reachable shipment is EUR-0312
    And the delay is 7 days and the delay severity is "critica"

  Scenario: Repainted units use the rework time
    Given a unit in "pintura" with retrabajos = 1
    When its projected yard arrival is computed
    Then the paint stage uses minutos_retrabajo instead of minutos_estandar

  Scenario: Units already in yard do not count for delay
    Given a unit in "patio" or "despacho"
    When the combination delay is computed
    Then that unit is excluded

  Scenario: Minimum severity is the worse of both
    Given gap severity "media" and delay severity "alta"
    Then the minimum severity is "alta" and the combination has a deviation
```
