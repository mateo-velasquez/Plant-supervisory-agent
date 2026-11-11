"""007 T10: 'emit_alert' and 'emit_shift_report' through the in-process client (R8, R9, E12, E13)."""

import json
from collections.abc import Sequence

import pytest
from draft_builders import MAX_CHARS, draft_frame, s003_notices, s004_notices
from mcp_builders import tool_context

from plant_monitor.agents.factory import COORDINATOR_TOOLS
from plant_monitor.cases.draft import NoticeDraft
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import READ_TOOLS, WRITE_TOOLS, build_server

from notice_builders import PICKUP_BRAZIL_CASE, PICKUP_LOCAL_CASE, SEDAN_LOCAL_CASE, SUV_LOCAL_CASE

pytestmark = pytest.mark.anyio

ALERT_ID = f"S003-alerta_inmediata-{SEDAN_LOCAL_CASE}"
NEWS_IDS = tuple(
    f"S004-informe_de_turno-{c}" for c in (SEDAN_LOCAL_CASE, PICKUP_LOCAL_CASE, PICKUP_BRAZIL_CASE)
)
SEL, PL, PB, SL = SEDAN_LOCAL_CASE, PICKUP_LOCAL_CASE, PICKUP_BRAZIL_CASE, SUV_LOCAL_CASE


def items(*pairs: tuple[str, str]) -> dict[str, object]:
    """Arguments of 'emit_shift_report' from '(case_id, texto)' pairs."""
    return {"textos": [{"case_id": case_id, "texto": texto} for case_id, texto in pairs]}


def err(tool: str, message: str) -> str:
    """The text a refusal arrives with."""
    return f"Error executing tool {tool}: {message}"


async def call(draft: NoticeDraft, calls: Sequence[tuple[str, dict[str, object]]]) -> list[tuple[str, bool]]:
    """Run 'calls' in order inside the draft's frame; return '(text, is_error)' of each."""
    ctx, frames = tool_context()
    results: list[tuple[str, bool]] = []
    with frames.entered(draft_frame(draft)):
        async with ToolClient(build_server(ctx, frames, tools=COORDINATOR_TOOLS)) as client:
            for name, arguments in calls:
                outcome = await client.call(name, arguments)
                results.append((outcome.text, outcome.is_error))
    return results


async def test_coordinator_tools_are_the_read_tools_plus_the_five_write_tools() -> None:
    """R8, R9, 006 E11: eleven tools offered with 'tools=', and the constant matches the server names."""
    assert set(COORDINATOR_TOOLS) <= {*READ_TOOLS, *WRITE_TOOLS}
    ctx, frames = tool_context()
    async with ToolClient(build_server(ctx, frames, tools=COORDINATOR_TOOLS)) as client:
        specs = await client.list_tools()
    assert sorted(spec.name for spec in specs) == sorted(COORDINATOR_TOOLS)


@pytest.mark.parametrize(
    ("call_", "message"),
    [
        pytest.param(
            ("emit_alert", {"case_id": PL, "texto": "x"}),
            err("emit_alert", f"no alerta_inmediata is decided for {PL} at S003"),
            id="not-decided",
        ),
        pytest.param(
            ("emit_alert", {"case_id": SEL, "texto": "  "}),
            err("emit_alert", f"texto for {SEL} is empty"),
            id="empty",
        ),
        pytest.param(
            ("emit_alert", {"case_id": SEL, "texto": "x" * 1501}),
            err("emit_alert", f"texto for {SEL} is 1501 characters, over the maximum of 1500"),
            id="too-long",
        ),
        pytest.param(
            ("emit_shift_report", {"textos": []}),
            err("emit_shift_report", "no shift report is decided at S003"),
            id="no-report-at-mid-snapshot",
        ),
    ],
)
async def test_e12_refusals_carry_the_full_text(call_: tuple[str, dict[str, object]], message: str) -> None:
    """E12: each refusal of the alert tool and the report tool at a mid snapshot."""
    draft = NoticeDraft(s003_notices(), MAX_CHARS)
    assert await call(draft, [call_]) == [(message, True)]
    assert draft.missing() == (ALERT_ID,)


async def test_e12_a_text_at_the_limit_is_written_once() -> None:
    """E12: 1,500 characters succeed, a second write is refused."""
    draft = NoticeDraft(s003_notices(), MAX_CHARS)
    first, second = await call(
        draft,
        [("emit_alert", {"case_id": SEL, "texto": "x" * 1500})] * 2,
    )
    assert first[1] is False
    assert json.loads(first[0]) == {"escritos": [ALERT_ID], "pendientes": []}
    assert second == (err("emit_alert", f"alerta_inmediata texto for {SEL} is already written"), True)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        pytest.param(items((SEL, "a"), (PL, "b")), f"missing texto for {PB}", id="missing-item"),
        pytest.param(
            items((SEL, "a"), (SL, "b"), (PL, "c"), (PB, "d")),
            f"{SL} is not a news item of T02",
            id="not-news",
        ),
        pytest.param(
            items((SEL, "a"), (SEL, "b"), (PL, "c"), (PB, "d")), f"{SEL} appears twice in textos", id="twice"
        ),
        pytest.param(items((SEL, "a"), (PL, "b"), (PB, "")), f"texto for {PB} is empty", id="empty-text"),
    ],
)
async def test_e13_report_refusals_write_nothing(arguments: dict[str, object], message: str) -> None:
    """E13: every refusal of the report tool leaves the three news missing."""
    draft = NoticeDraft(s004_notices(), MAX_CHARS)
    assert await call(draft, [("emit_shift_report", arguments)]) == [
        (err("emit_shift_report", message), True)
    ]
    assert draft.missing() == NEWS_IDS


async def test_e13_a_valid_report_is_written_once() -> None:
    """E13: the valid list writes the three news; a second call is refused."""
    draft = NoticeDraft(s004_notices(), MAX_CHARS)
    valid = items((SEL, "a"), (PL, "b"), (PB, "c"))
    first, second = await call(draft, [("emit_shift_report", valid)] * 2)
    assert first[1] is False
    assert json.loads(first[0]) == {"escritos": list(NEWS_IDS), "pendientes": []}
    assert second == (err("emit_shift_report", "shift report texts for T02 are already written"), True)
    assert draft.missing() == ()
