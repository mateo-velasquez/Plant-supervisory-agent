"""011 T4: the loop hashes its cached prefix and feeds the drift monitor (R8-R10, E10, E11c, E11c', E11d)."""

import logging
from decimal import Decimal

import pytest
from agent_builders import OFFERED, USAGE, FakeProgress, FakeTools, end, make_coordinator, tools_reply

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import Coordinator, LoopLog, compose_system
from plant_monitor.agents.prefix import PrefixMonitor, prefix_hash
from plant_monitor.mcp_server.types import ToolSpec
from plant_monitor.telemetry.trace import TraceLine, build_line, run_totals
from plant_monitor.telemetry.usage import PriceCard, Usage

from builders import CRIT

pytestmark = pytest.mark.anyio

LOGGER = "plant_monitor.agents.prefix"
CARD = PriceCard(
    input=Decimal("0.10"),
    cache_write_5m=Decimal("0.125"),
    cache_write_1h=Decimal("0.20"),
    cache_read=Decimal("0.01"),
    output=Decimal("0.50"),
    long_context_threshold=100_000,
    long_context_multiplier=Decimal(5),
)
U1 = Usage(input_tokens=300, output_tokens=50, cache_write_5m_tokens=2000)
U2 = Usage(input_tokens=400, output_tokens=60, cache_read_tokens=2000, cache_write_5m_tokens=350)
U3 = Usage(input_tokens=120, output_tokens=40, cache_read_tokens=2350)
U4 = Usage(input_tokens=300, output_tokens=50, cache_read_tokens=2000)


def sanitized(suffix: str = "") -> tuple[ToolSpec, ...]:
    """The tools 'FakeTools' lists, after the sanitizer."""
    schema = {"type": "object", "additionalProperties": False}
    return tuple(ToolSpec(name, f"{name} tool{suffix}", schema) for name in OFFERED)


def line_of(snapshot_id: str, log: LoopLog) -> TraceLine:
    return build_line(
        snapshot_id=snapshot_id,
        turno_id="T01",
        status="committed",
        decision="call",
        decision_reason="text_needed",
        outcome="done",
        required=[],
        model_calls=log.model_calls,
        tool_calls=log.tool_calls,
        thinking=log.thinking,
        notices_agent=[],
        notices_template=[],
        report_id=None,
        card=CARD,
    )


def warnings_of(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == LOGGER]


async def two_runs(
    coordinator: Coordinator, tools: FakeTools, between: str | None = None, *, suffix: str | None = None
) -> tuple[LoopLog, LoopLog]:
    """Run S003 then S004 on one loop, optionally changing the criteria or the suffix in between."""
    first, second = LoopLog(), LoopLog()
    await coordinator.run("S003", "brief A", FakeProgress(), first)
    if between is not None:
        tools.criteria = between
    if suffix is not None:
        tools.suffix = suffix
    await coordinator.run("S004", "brief B", FakeProgress(), second)
    return first, second


async def test_e10_the_prefix_hash_is_stable_across_briefs_and_cache_sums_reach_the_trace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """E10: 4 records share one hash (brief never enters it); no drift warning; cache sums and cost."""
    tools = FakeTools(FakeProgress())
    model = FakeModel(
        [
            tools_reply(("get_deviations", {}), prefix="tu", usage=U1),
            tools_reply(("get_case", {"case_id": "S001-Sedán-Local"}), prefix="tv", usage=U2),
            end("Listo.", U3),
            end("Listo.", U4),
        ]
    )
    coordinator = make_coordinator(model, tools, criteria_prompt="criteria", prefix_monitor=PrefixMonitor())
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        first, second = await two_runs(coordinator, tools)
    expected = prefix_hash(compose_system("SYSTEM", CRIT), sanitized(), None)
    assert [c.prefix_hash for c in (*first.model_calls, *second.model_calls)] == [expected] * 4
    assert warnings_of(caplog) == []
    lines = [line_of("S003", first), line_of("S004", second)]
    assert [c.prefix_hash for c in lines[0].model_calls] == [expected] * 3
    assert (lines[0].totals.input_tokens, lines[0].totals.output_tokens) == (820, 150)
    assert (lines[0].totals.cache_read_tokens, lines[0].totals.cache_write_5m_tokens) == (4350, 2350)
    assert lines[0].totals.usd == Decimal("0.00049425")
    assert lines[1].totals.cache_read_tokens == 2000
    assert lines[1].totals.usd == Decimal("0.000075")
    totals = run_totals(lines)
    assert (totals.input_tokens, totals.output_tokens) == (1120, 200)
    assert (totals.cache_read_tokens, totals.cache_write_5m_tokens) == (6350, 2350)
    assert totals.usd == Decimal("0.00056925")
    agent = totals.by_agent["coordinator"]
    assert (agent.cache_read_tokens, agent.cache_write_5m_tokens, agent.cache_write_1h_tokens) == (
        6350,
        2350,
        0,
    )


@pytest.mark.parametrize(
    ("criteria", "suffix"),
    [
        pytest.param(CRIT + "Extra.\n", None, id="c-criteria-changed"),
        pytest.param(None, " v2", id="c-prime-tool-descriptions-changed"),
    ],
)
async def test_e11c_a_changed_prefix_between_runs_warns_with_both_hashes(
    criteria: str | None, suffix: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """E11 (c), (c'): changed criteria or tool descriptions warn once at the next snapshot."""
    tools = FakeTools(FakeProgress())
    model = FakeModel([end("Listo.", U1), end("Listo.", U4)])
    coordinator = make_coordinator(model, tools, criteria_prompt="criteria", prefix_monitor=PrefixMonitor())
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        first, second = await two_runs(coordinator, tools, criteria, suffix=suffix)
    old, new = first.model_calls[0].prefix_hash, second.model_calls[0].prefix_hash
    assert old is not None
    assert new is not None
    assert old != new
    assert warnings_of(caplog) == [f"coordinator prefix changed at S004: {old} -> {new}"]


async def test_e11d_without_a_monitor_nothing_warns_and_records_keep_the_hash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """E11 (d): no 'prefix_monitor' means no WARNING, but every record still carries 'prefix_hash'."""
    tools = FakeTools(FakeProgress())
    model = FakeModel([tools_reply(("get_deviations", {}), usage=USAGE), end("Listo.", USAGE)])
    log = LoopLog()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await make_coordinator(model, tools).run("S003", "brief", FakeProgress(), log)
    assert warnings_of(caplog) == []
    assert len(log.model_calls) == 2
    assert all(c.prefix_hash is not None and len(c.prefix_hash) == 64 for c in log.model_calls)
