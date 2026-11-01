# Architecture Decision Records

One file per significant decision: `NNNN-short-title.md`, numbered in order, never renumbered. A changed decision gets a new ADR that supersedes the old one.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-use-uv.md) | Use uv for environment and dependencies | Accepted |
| [0002](0002-code-computes-model-judges.md) | Code computes and enforces; the model judges and writes | Accepted |
| [0003](0003-single-writer-sqlite-registry.md) | Case registry in SQLite with a single writer | Accepted |
| [0004](0004-data-not-versioned.md) | Real data not versioned; synthetic fixtures for tests | Accepted |
| [0005](0005-english-code-spanish-data-contract.md) | English code; Spanish data-contract values | Accepted |
| [0006](0006-claude-code-dev-workflow.md) | Claude Code workflow: scoped subagents, skills and guard hooks | Accepted |
| [0007](0007-own-agent-loop-with-mcp-client.md) | Own agent loop on the Anthropic SDK, connected to our MCP server | Proposed |

Template: [template.md](template.md)
