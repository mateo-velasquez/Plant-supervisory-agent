# US-11 · Run the full series unattended, with cost

**As a** developer, **I want** one command that runs the whole series and reports cost and time, **so that** runs are reproducible and comparable.

**Requirements:** FR-33, FR-36, FR-37, NFR-02, NFR-10

## Acceptance criteria
```gherkin
Feature: Unattended run

  Scenario: Full series in one command
    When I run the series command
    Then the 61 arrivals are processed in order without manual steps
    And 30 shift reports are produced

  Scenario: Cost and time are reported
    When a run ends
    Then it reports input, output and cache-read tokens, cost in USD and duration

  Scenario: Prompt budget guard
    Given a request would exceed 100k prompt tokens
    Then it is not sent and the run reports which step exceeded it

  Scenario: Resume after failure
    Given the run failed at S030
    When I run it again
    Then processing resumes at S030 without reprocessing S001–S029
```
