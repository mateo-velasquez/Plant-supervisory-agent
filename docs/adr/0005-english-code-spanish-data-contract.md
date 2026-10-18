# 0005 · English code; Spanish data-contract values

- **Status:** Accepted
- **Date:** 2026-10-18
- **Requirements:** FR-25, NFR-08

## Context
The team wants professional, English code and docs. The input data, the criteria and the expected output use Spanish names (`abierto`, `parada_de_linea`, `alerta_inmediata`, `etapa`, `mercado`).

## Decision
Identifiers, comments, docs and commits are in English. **Values** of the data contract keep the spec's Spanish spelling: enum values, JSON field names in inputs and outputs, and file names. Example: `class CaseState(StrEnum): OPEN = "abierto"`.

## Alternatives considered
- **All Spanish:** matches the domain but reads less professionally for the target audience.
- **Translate the contract too:** output would no longer match the brief's format, and every boundary would need mapping.

## Consequences
- Positive: idiomatic code with an output that matches the brief exactly.
- Negative: a bilingual seam; field aliases are needed where Python names differ from JSON keys.
