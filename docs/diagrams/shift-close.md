# Shift close

```mermaid
flowchart TD
    close[Closing snapshot processed] --> news[Novelty rules compute expected news<br/>new · resolved · state/severity changed · in-shift peak]
    news --> active[Collect active cases<br/>gap · delay · severity · max severity · state · bottleneck]
    active --> agent[Coordinator drafts report text<br/>using causes and citations]
    agent --> submit[emit_shift_report]
    submit --> stop{On-stop hook}
    stop -- missing active case --> reject[Tool error: name missing cases] --> agent
    stop -- news repeated without change --> reject2[Tool error: no news since last report] --> agent
    stop -- complete --> persist[Persist report + last reported state per case]
    persist --> out[Notifier: console + file per shift]
```

The code decides **which** cases are news and which are active, and the agent decides **how** to say it. The hook makes sure the agent's report matches the code's expectation exactly.
