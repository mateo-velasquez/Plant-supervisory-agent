# 014 · Visual shift reports (stretch) — Plan

## Modules

| File | Responsibility |
|---|---|
| `notify/html.py` | HTML notifier adapter. |
| `notify/templates/` | Page templates (shift report, alert, run index). |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
Ports and Adapters: one more adapter, no change to the core. HTML output is escaped, since causes quote free-text logbooks.

## Test strategy
Snapshot tests of rendered HTML from synthetic reports; an escaping test with a logbook fragment containing markup.

## Risks
Time: this is the first thing cut if the plan slips.
