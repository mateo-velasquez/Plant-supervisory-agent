# 0007 · Own agent loop on the Anthropic SDK, connected to our MCP server

- **Status:** Accepted (transport and client location revised by [ADR-0013](0013-in-process-mcp-transport-and-tool-client.md))
- **Date:** 2026-10-31
- **Requirements:** FR-27, FR-31, FR-32, FR-33, NFR-07, NFR-10

## Context
The agents need a loop that calls Claude Haiku 5.5, runs tools from our own MCP server (FR-27), and wraps every tool call with hooks before, after and on stop (FR-31). Allowlists must be enforced in code (FR-32). Module 5 of the course teaches these concepts "without Claude Code, in your own code", and the course requires `anthropic`, `mcp` and `pydantic`. CI must test the agent layer with a fake model (NFR-07).

## Decision
We write the agent loop ourselves on the `anthropic` Messages API with tool use. The loop connects to our server through an MCP client, offers each agent only its allowlisted tools, and runs the hook chain around every tool call and at stop. Transport: in-process in real runs and in tests, through the `mcp_server/client.py` adapter (decided in spec 006, [ADR-0013](0013-in-process-mcp-transport-and-tool-client.md)).

## Alternatives considered
- **Claude Agent SDK:** has hooks and MCP built in, but it hides the loop the course asks us to build, couples runs to the Claude Code runtime, and makes fake-model tests harder.
- **SDK tool runner (beta):** less code, but less control over where hooks run and how tool errors return to the model.
- **Domain functions as plain tools, without MCP:** simpler, but it breaks FR-27.

## Consequences
- Positive: full control over hooks, allowlists, retries and token accounting; integration tests run against a fake model with no network.
- Negative / risks: more code to own (loop, retries with backoff, stop conditions, cost accounting).
- Follow-ups:
  - ~~Decide where the `mcp` client is imported~~: done in spec 006, a thin adapter in `mcp_server/client.py`, so only `mcp_server` imports `mcp` (ADR-0013).
  - ~~Before spec 007, check Haiku 5.5 parameters against the current API docs~~: done 2026-11-08 (spec 007 D1). Thinking is adaptive only (`budget_tokens` returns 400) and its blocks go back unmodified in an append-only history; `effort` defaults to `medium`; sampling parameters return 400; the minimum cacheable prefix is 512 tokens; $0.10 / $0.50 per MTok up to 100k prompt tokens and ×5 above. The loop contract is [ADR-0014](0014-coordinator-loop-contract.md).
  - ~~Set this ADR to Accepted once spec 006 confirms the transport~~: done (ADR-0013).
