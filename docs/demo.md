# Demo Day script (draft)

**Status:** draft (spec 013 T5). The alert, the real `notice_id`, the timings and the fallback are finished after the held-out run (013 T4, T11), and each of those steps needs the user's permission. Rehearsal: 013 T6.

## What the demo shows
1. The full series running live, one snapshot at a time, with alerts and shift reports appearing as they commit.
2. The run's cost and duration (the summary printed at the end).
3. The trace of one alert, from snapshot to logbook quote, rebuilt only from stored data (`plant-monitor trace`, no model call, nothing written).

## Steps and timings

The slot length is not fixed yet; times below are placeholders to adjust in the rehearsal.

| # | Step | Command | Time (placeholder) |
|---|---|---|---|
| 1 | Context: the plant, the brief and the rules (`criterio.md`, `umbrales.yaml`) | — | 1 min |
| 2 | Live run, paced so the audience can follow | `uv run plant-monitor run --speed <s>` | TBD (61 arrivals × (`<s>` + processing)) |
| 3 | Summary: tokens, cache, USD, duration, alerts, reports | printed by step 2 | 1 min |
| 4 | Trace of the chosen alert | `uv run plant-monitor trace <notice_id>` | 2 min |
| 5 | Questions | — | rest |

Notes:
- Step 2 runs in a fresh `OUTPUT_DIR`. If the slot is too short for the whole series at a readable pace, run `--until <snapshot>` live and switch to the recorded directory for the rest (see Fallback).
- `--speed` only pauses after each committed snapshot; it never changes what the system decides.
- Step 4 is read-only: it can run against the live directory after step 2 finishes, or against the recorded copy.

## Candidate alerts

Both are expected from the criteria and the days 1–7 analysis (roadmap, "Known findings"). Neither `notice_id` is confirmed until the held-out run exists (013 T4).

| Candidate | Story | Expected alert | What the trace shows |
|---|---|---|---|
| Europe homologation audit | T07 says the audit "retuvo en calidad las SUV de exportación", with no date. The agent raises at the T07 close (S014). SUV × Europa opens already escalated at S015 (Q-08, Q-39). T10 lifts the raise (S020). | `S015-alerta_inmediata-S015-SUV-Europa` (to confirm) | `motivo [bitacora]`, `origen agente`, the raise opened at S014 with the T07 quote and the investigator's proposal, the transition `— → escalado` |
| Pickup assembly stop | T17 says "no hay fecha confirmada de vuelta". The agent raises at the T17 close (S034); the Pickup cases open escalated. T19 reports the line back (S038). | `S034-alerta_inmediata-S034-Pickup-Local` (to confirm) | Same shape, plus the gap that keeps the cases `critica` after the lift. Needs permission to read S033–S040 and T17–T19 (also blocks the 008 T18 goldens). |

Choice criteria (T4): the trace must be complete (metrics, transition, quote, proposal, tool calls), readable in one screen, and every line must check by hand against `criterio.md` (§1–§2 metrics, §3 transition, §5 raise, §6 cause and quote).

## Dry run on synthetic fixtures

No real data and no API key needed:

```powershell
uv run pytest tests/integration/test_trace_cli.py --basetemp z_helps/dry-run
```

It leaves the agent and threshold-only `OUTPUT_DIR`s of the tests under `z_helps/dry-run/`. Point `OUTPUT_DIR` at one of them and run `uv run plant-monitor trace <notice_id>` to rehearse the trace step (the ids are the ones in spec 013, E1–E3).

## Fallback

*To finish after the held-out run (013 T11).*
- A copy of the held-out run's `OUTPUT_DIR`, kept outside the repo, plus the saved output of `plant-monitor trace` for the chosen alert.
- If the live run fails or the network is down: show the recorded summary (`OUTPUT_DIR/runs/run-<ts>.json`) and run `plant-monitor trace` against the copy. The trace needs no network and no key.
- If the terminal cannot show a character, `trace` writes with `backslashreplace` and never crashes on encoding.
