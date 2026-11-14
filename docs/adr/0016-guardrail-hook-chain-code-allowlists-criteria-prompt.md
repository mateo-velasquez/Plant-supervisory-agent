# 0016 · Guardrail hook chain, code allowlists and criteria MCP prompt

- **Status:** Accepted
- **Date:** 2026-11-11
- **Requirements:** FR-15, FR-20, FR-30, FR-31, FR-32, FR-33, NFR-06 (Q-43, Q-44, Q-46, Q-55)

## Context
Spec 010 must add hooks before each tool, after each tool and on stop (FR-31), enforce per-agent allowlists in code (FR-32) and serve the criteria as an MCP prompt (FR-30). Since 007 and 009 the model cannot break FR-31 as literally written:
- code decides every notice, its severity and the news set;
- the notice draft already refuses undecided alerts (`NoticeNotDecided`), non-news cases (`NotNews`) and incomplete reports (`MissingNews`);
- `apply_proposal` only raises the floor or restores it.

The only free model output that reaches the user is `texto`, and Q-46 left "the text states only the notice's cause" to the prompt, with hooks deferred to 010. The 008 judgment tools stay registered but are offered to no agent (ADR-0009, X9). The loop has one tool-call seam (`ToolPort.call`) and one end-of-turn seam (`EndReview`) for both agents.

## Decision
- **Hook chain (Chain of Responsibility)** injected into the agent loop for both agents, with three phases:
  - **pre-tool:** may block. The call never reaches the server, and the reason returns as a tool error.
  - **post-tool:** verify only. The write already happened, so a violation is a code bug, never the model's fault: it raises and aborts the snapshot.
  - **on-stop:** wraps `EndReview`. A block returns as a note, and a second note ends in the review's exhausted fallback.
- **What the hooks check.** They reuse the code's decisions (the draft's required set from `cases/novelty.py`, the decision's minimum severity, the notice's `causa`) and never recompute a rule:
  - **allowlist (pre):** a tool outside the agent's list is blocked;
  - **novelty (pre):** an emit for a case that is not decided news or alert is blocked with "no news since last report";
  - **floor:**
    - (pre) a `texto` stating a severity below its notice's `severidad` is blocked with "below notice severity (<level>)";
    - (post) after `apply_proposal`, every changed notice keeps `severidad` ≥ its computed minimum;
  - **cause (pre):** a `texto` naming a §6 category other than its notice's `causa` is blocked, enforcing Q-46 in code; a category word describing data counts too (Q-55);
  - **completeness (on-stop):** ending with required texts unwritten is blocked, naming the missing case. It replaces `MissingTexts` inside the chain.
- **Allowlists:** `agents/allowlists.py` is the single source, per agent, with an explicit `EXCLUDED` set (`set_cause`, `raise_severity`, `lift_severity_raise`). Three barriers enforce it:
  - a test that no list meets `EXCLUDED`;
  - the allowlist hook;
  - a `ValueError` at the composition root.

  The excluded tools stay registered in `build_server`, so their tests stay.
- **Criteria prompt:** the server registers the MCP prompt `criteria` with the full `criterio.md`, whose text the composition root passes in through `ToolContext`. `ToolPort` gains `get_prompt`, and each agent's system becomes its role prompt plus a `<criterios>` block, which complements and does not replace the packaged prompts.
- **Failure policy (Q-43):**
  - repeated blocks consume turns and end in `fallback:turn_cap`, with no new limit;
  - an internal error inside a hook aborts the snapshot (fail-closed, resumable).
- **Trace (Q-44):** `hooks` holds one record per block: agent, phase, hook, tool, turn and reason.

## Alternatives considered
- **Hooks that only repeat the draft's structural refusals:** they protect nothing the draft does not already protect, and they leave `texto` unchecked.
- **Post-tool hooks that undo writes:** the ledger writes inside the open unit of work. Undoing a write would need compensating writes, which is more state for a case that only a code bug can produce.
- **Removing the 008 judgment tools from the server:** cleaner wiring, but it deletes tested code and the tests with it. The allowlist and the composition check cover the wiring risk.
- **Criteria split per agent:** fewer tokens (about 1,500 per request in total), but a cut-down copy to keep in sync.
- **Fail-open hooks:** keep the series moving, but a broken guardrail would silently stop protecting.

## Consequences
- Positive:
  - The model's only free output is checked in code.
  - Allowlists have one source and three barriers.
  - Every block is visible in the trace.
  - The system prefix (role plus criteria) is stable across snapshots, ready for 011's cache.
- Negative / risks:
  - The text checks match fixed patterns ("severidad <nivel>", §6 categories), so a paraphrase can slip through. Patterns stay narrow to avoid false positives on common words ("alta", "media").
  - Each request carries about 1,500 more tokens.
  - A line injected verbatim into a later logbook still passes `verify_citation` (ADR-0009); its worst effect is a lift back to the code floor.
- Follow-ups:
  - Spec 011 caches the role plus criteria prefix and adds structured-output validation as another on-stop review.
  - Spec 012 adds the one-command run.
  - Renaming `Coordinator` to `AgentLoop` stays deferred.
