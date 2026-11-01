# 008 · Cited cause and logbook escalation — Plan

## Modules

| File | Responsibility |
|---|---|
| `domain/causes.py` | `CauseCategory`, `Cause`, `Evidence`, `ActiveCause` (scope, opened by, lifted by). |
| `cases/causes.py` | Scope matching (Q-02), "raise in force" per case, application to new cases. |
| `cases/registry.py` | Tables for causes per case and active causes. |
| `mcp_server/write_tools.py` | `set_cause`, `raise_severity`, `lift_severity_raise`. |
| `agents/prompts/coordinator.md` | Prompt v2: cause extraction and escalation rules (§5–§6). |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
- The raise enters the lifecycle (spec 003) as `raise_in_force`, so effective severity and resolution stay in one place.
- The escalation alert from a raise reuses spec 004's alert rule with `origen=agente`.

## Test strategy
Unit tests for the tools and scope matching; integration with `FakeModel` scripting the three incidents; on-demand evals with Haiku on days 1–7.

## Risks
A scope that is too broad multiplies alerts; one that is too narrow misses US-07's second scenario. Both are covered by evals.
