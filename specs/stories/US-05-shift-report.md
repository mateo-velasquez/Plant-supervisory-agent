# US-05 · Read a shift report with only what changed

**As a** plant manager, **I want** each end-of-shift report to list only what changed plus the table of active cases, **so that** I read news, not repetition.

**Requirements:** FR-22, FR-23, FR-24

## Acceptance criteria
```gherkin
Feature: Shift report

  Scenario: A report at every closing snapshot
    When the closing snapshot of a shift is processed
    Then exactly one "informe_de_turno" is emitted for that shift

  Scenario: New and resolved cases are news
    Given during the shift one case opened and another was resolved
    Then both appear in "novedades"

  Scenario: Unchanged cases are not news
    Given a case was "en_seguimiento" at "alta" in the previous report
    And it is still "en_seguimiento" at "alta"
    Then it is not in "novedades"
    But it is in "casos_activos"

  Scenario: abierto and en_seguimiento count as the same state
    Given a case was "abierto" in the previous report
    And it is "en_seguimiento" with the same severity now
    Then it is not in "novedades"

  Scenario: A peak between reports is not lost
    Given a case went from "media" to "alta" and back to "media" within the shift
    Then it is in "novedades" with current severity "media" and max severity "alta"

  Scenario: Every active case is listed
    Then "casos_activos" lists every active case with gap, delay, severity, state and bottleneck stage
```
