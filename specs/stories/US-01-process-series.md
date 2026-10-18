# US-01 · Process the series once per snapshot

**As a** production control analyst, **I want** every snapshot processed exactly once and in arrival order, **so that** a resent file never produces duplicate cases or notices.

**Requirements:** FR-01, FR-02, FR-03, FR-04

## Acceptance criteria
```gherkin
Feature: Snapshot ingestion

  Scenario: Snapshots are processed in arrival order
    Given llegadas.csv lists S001, S002 and S003 in that order
    When the series runs
    Then the snapshots are processed as S001, S002, S003

  Scenario: A repeated snapshot is ignored
    Given S034 has already been processed
    When S034 arrives again
    Then no case, notice or state changes
    And the run log records "S034 skipped: already processed"

  Scenario: CSV files with BOM are read correctly
    Given a CSV whose first bytes are a UTF-8 BOM
    When it is loaded
    Then the first column name has no BOM prefix

  Scenario: Malformed input fails loudly
    Given a snapshot whose unit lacks "etapa"
    When it is loaded
    Then loading fails with an error naming the file and the field

  Scenario: Closing snapshots are identified
    Given turnos.csv says T01 closes at S002
    When S002 is processed
    Then it is flagged as the closing snapshot of T01
```
