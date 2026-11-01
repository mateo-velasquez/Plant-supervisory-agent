# 0007 · Own agent loop on the Anthropic SDK, connected to our MCP server

- **Status:** Proposed
- **Date:** 2026-10-31
- **Requirements:** FR-27, FR-31, FR-32, FR-33, NFR-07, NFR-10

## Context
The agents need a loop that calls Claude Haiku 5.5, runs tools from our own MCP server (FR-27), and wraps every tool call with hooks before, after and on stop (FR-31). Allowlists must be enforced in code (FR-32). Module 5 of the course teaches these concepts "without Claude Code, in your own code", and the course requires `anthropic`, `mcp` and `pydantic`. CI must test the agent layer with a fake model (NFR-07).

## Decision
We write the agent loop ourselves on the `anthropic` Messages API with tool use. The loop connects to our server through an MCP client, offers each agent only its allowlisted tools, and runs the hook chain around every tool call and at stop. Transport: stdio subprocess in real runs and in-process in tests (to confirm in spec 006).

## Alternatives considered
- **Claude Agent SDK:** has hooks and MCP built in, but it hides the loop the course asks us to build, couples runs to the Claude Code runtime, and makes fake-model tests harder.
- **SDK tool runner (beta):** less code, but less control over where hooks run and how tool errors return to the model.
- **Domain functions as plain tools, without MCP:** simpler, but it breaks FR-27.

## Consequences
- Positive: full control over hooks, allowlists, retries and token accounting; integration tests run against a fake model with no network.
- Negative / risks: more code to own (loop, retries with backoff, stop conditions, cost accounting).
- Follow-ups:
  - The dependency rule in `docs/STRUCTURE.md` says only `mcp_server` imports `mcp`, but the client side also needs it. Decide in spec 006: either `agents` may import the `mcp` client, or a thin client adapter lives in `mcp_server/`.
  - Before spec 007, check Haiku 5.5 parameters (`effort`, thinking, minimum cacheable prefix, pricing) against the current API docs.
  - Set this ADR to Accepted once spec 006 confirms the transport.
