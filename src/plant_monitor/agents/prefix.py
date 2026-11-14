"""Prefix bytes, hash and drift monitor of the cached prompt prefix (011 R8, R9)."""

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence

from plant_monitor.mcp_server.types import ToolSpec
from plant_monitor.telemetry.trace import AgentName
from plant_monitor.telemetry.usage import Usage

logger = logging.getLogger(__name__)

FIRST_CACHED_TURN = 2


def prefix_bytes(system: str, tools: Sequence[ToolSpec], output_schema: Mapping[str, object] | None) -> bytes:
    """Canonical bytes of what precedes the messages: system, tools and output format."""
    content = {
        "system": system,
        "tools": [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools
        ],
        "output_schema": output_schema,
    }
    text = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=dict)
    return text.encode("utf-8")


def prefix_hash(system: str, tools: Sequence[ToolSpec], output_schema: Mapping[str, object] | None) -> str:
    """The sha256 hex digest of the prefix bytes."""
    return hashlib.sha256(prefix_bytes(system, tools, output_schema)).hexdigest()


class PrefixMonitor:
    """Warns when an agent's prefix changes between runs or a later call reads no cache; never raises."""

    def __init__(self) -> None:
        self._last: dict[AgentName, str] = {}

    def on_run(self, agent: AgentName, snapshot_id: str, prefix_hash: str) -> None:
        """Warn when the agent's hash differs from its previous run's."""
        previous = self._last.get(agent)
        if previous is not None and previous != prefix_hash:
            logger.warning("%s prefix changed at %s: %s -> %s", agent, snapshot_id, previous, prefix_hash)
        self._last[agent] = prefix_hash

    def on_call(self, agent: AgentName, snapshot_id: str, turn: int, usage: Usage, prefix_hash: str) -> None:
        """Warn when a call after the first read no cached tokens."""
        if turn >= FIRST_CACHED_TURN and usage.cache_read_tokens == 0:
            logger.warning(
                "%s call %d at %s read no cached tokens (prefix %s)", agent, turn, snapshot_id, prefix_hash
            )
