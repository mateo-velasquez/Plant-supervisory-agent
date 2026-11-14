"""011 T2: prefix bytes, hash and drift monitor (R8, R9, E9, E11a, E11b)."""

import hashlib
import logging
from types import MappingProxyType

import pytest

from plant_monitor.agents.prefix import PrefixMonitor, prefix_bytes, prefix_hash
from plant_monitor.mcp_server.types import ToolSpec
from plant_monitor.telemetry.usage import Usage

LOGGER = "plant_monitor.agents.prefix"
SCHEMA = {"type": "object", "additionalProperties": False}
TOOL = ToolSpec("get_case", "One case.", SCHEMA)
OTHER = ToolSpec("get_deviations", "Deviations.", SCHEMA)
OUT = {"type": "object", "properties": {"propuestas": {"type": "array"}}, "required": ["propuestas"]}
EXPECTED = (
    b'{"output_schema":null,"system":"ROLE","tools":[{"description":"One case.",'
    b'"input_schema":{"additionalProperties":false,"type":"object"},"name":"get_case"}]}'
)


def test_e9_prefix_bytes_are_canonical_and_the_hash_is_sha256() -> None:
    """E9 (a), (b): exact bytes; key order of the schema does not matter."""
    swapped = ToolSpec("get_case", "One case.", {"additionalProperties": False, "type": "object"})
    data = prefix_bytes("ROLE", (TOOL,), None)
    assert data == EXPECTED
    assert prefix_bytes("ROLE", (swapped,), None) == data
    digest = prefix_hash("ROLE", (TOOL,), None)
    assert digest == hashlib.sha256(data).hexdigest()
    assert len(digest) == 64
    assert digest == digest.lower()


@pytest.mark.parametrize(
    ("system", "tools", "output_schema"),
    [
        pytest.param("ROLE", (TOOL,), OUT, id="output_schema"),
        pytest.param("ROLE ", (TOOL,), None, id="system"),
        pytest.param("ROLE", (ToolSpec("get_case", "One case!", SCHEMA),), None, id="description"),
    ],
)
def test_e9_any_content_change_changes_the_hash(
    system: str, tools: tuple[ToolSpec, ...], output_schema: dict[str, object] | None
) -> None:
    """E9 (c), (d): output schema, system and description each change the hash."""
    assert prefix_hash(system, tools, output_schema) != prefix_hash("ROLE", (TOOL,), None)


def test_e9_swapping_two_tools_changes_the_hash() -> None:
    """E9 (d): tool order is part of the prefix."""
    assert prefix_hash("ROLE", (TOOL, OTHER), None) != prefix_hash("ROLE", (OTHER, TOOL), None)


def test_e9_risk_a_non_dict_mapping_schema_hashes_like_a_dict() -> None:
    """Risk: a 'MappingProxyType' schema makes 'json.dumps' raise or hash differently (R8 'default=dict')."""
    proxy = ToolSpec("get_case", "One case.", MappingProxyType(SCHEMA))
    assert prefix_bytes("ROLE", (proxy,), None) == EXPECTED


def test_e11a_a_changed_hash_warns_once_per_agent(caplog: pytest.LogCaptureFixture) -> None:
    """E11 (a): only the coordinator's H1 -> H2 at S005 warns; the investigator's H3 never counts."""
    monitor = PrefixMonitor()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        monitor.on_run("coordinator", "S003", "H1")
        monitor.on_run("investigator", "S004", "H3")
        monitor.on_run("coordinator", "S004", "H1")
        monitor.on_run("coordinator", "S005", "H2")
        monitor.on_run("coordinator", "S006", "H2")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == LOGGER]
    assert [r.getMessage() for r in warnings] == ["coordinator prefix changed at S005: H1 -> H2"]


def test_e11b_a_later_call_with_no_cache_read_warns(caplog: pytest.LogCaptureFixture) -> None:
    """E11 (b): turn 1 never warns; turn 2 with read 0 warns; turn 3 with a read does not."""
    monitor = PrefixMonitor()
    first = Usage(input_tokens=1, output_tokens=1, cache_write_5m_tokens=2000)
    miss = Usage(input_tokens=1, output_tokens=1)
    hit = Usage(input_tokens=1, output_tokens=1, cache_read_tokens=5)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        monitor.on_call("coordinator", "S003", 1, first, "H1")
        monitor.on_call("coordinator", "S003", 2, miss, "H1")
        monitor.on_call("coordinator", "S003", 3, hit, "H1")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == LOGGER]
    assert [r.getMessage() for r in warnings] == [
        "coordinator call 2 at S003 read no cached tokens (prefix H1)"
    ]
