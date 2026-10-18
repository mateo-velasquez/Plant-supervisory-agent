# US-12 · Know if a change improved or broke the system

**As a** developer, **I want** an evaluator over hand-verified golden cases, **so that** every change is measured instead of eyeballed.

**Requirements:** FR-39, FR-40

## Acceptance criteria
```gherkin
Feature: Evaluator

  Scenario: Alerts are checked for timing and uniqueness
    Given a golden case expects one alert for a case at S020
    Then the evaluator reports a hit only if exactly one alert fired at S020

  Scenario: Missing and extra news are both errors
    Given a golden shift report
    Then missing news and extra news are each counted as errors

  Scenario: Causes are checked against the source
    Then each cause is checked for categoria, etapa and that the fragment exists in the cited logbook

  Scenario: Noise needs no golden data
    Then the evaluator counts news repeated unchanged from the previous report

  Scenario: Held-out days stay held out
    Given the current week is before W5
    When the evaluator runs
    Then it refuses to load shifts T22–T30
```
