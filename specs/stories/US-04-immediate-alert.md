# US-04 · Get one alert when a case escalates

**As a** plant manager, **I want** an immediate alert the moment a case becomes critical, and only once, **so that** I act on time without being paged repeatedly for the same problem.

**Requirements:** FR-21, FR-25

## Acceptance criteria
```gherkin
Feature: Immediate alert

  Scenario: Alert in the escalation snapshot
    Given a case is "en_seguimiento" with severity "alta"
    When snapshot S020 raises its severity to "critica"
    Then an "alerta_inmediata" is emitted with snapshot_id "S020"

  Scenario: One alert per case
    Given a case is already "escalado" and was alerted
    When later snapshots keep it at "critica"
    Then no further alert is emitted for that case

  Scenario: Alert records origin and evidence
    When an alert is emitted
    Then it records modelo, mercado, severidad, estado and origen ("umbral" or "agente")
    And it records causa {categoria, etapa} and evidencia [{bitacora, fragmento}]
    And texto explains why it escalated
```
