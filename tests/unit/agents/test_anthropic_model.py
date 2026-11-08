"""007 T8: 'AnthropicModel' retries and SDK conversion over a mock HTTP transport (E10, E11)."""

import json
from collections.abc import Sequence
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from plant_monitor.agents.anthropic_model import (
    AnthropicModel,
    RetryPolicy,
    from_message,
    to_params,
)
from plant_monitor.agents.model import (
    Message,
    ModelCallFailed,
    ModelRequest,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from plant_monitor.mcp_server.types import ToolSpec
from plant_monitor.telemetry.usage import Usage

pytestmark = pytest.mark.anyio

KEY = "sk-ant-test-secret-key"
MODEL_NAME = "claude-haiku-5-5"


def error_response(status: int) -> httpx2.Response:
    """An API error body that echoes the key, to prove it never reaches 'ModelCallFailed'."""
    body = {"type": "error", "error": {"type": "api_error", "message": f"bad key {KEY}"}}
    return httpx2.Response(status, json=body)


def message_json(usage: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": MODEL_NAME,
        "content": [
            {"type": "thinking", "thinking": "Busco desvíos.", "signature": "sig-1"},
            {"type": "redacted_thinking", "data": "opaque-1"},
            {"type": "tool_use", "id": "tu-1", "name": "get_deviations", "input": {"a": 1}},
        ],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": usage
        or {
            "input_tokens": 1200,
            "output_tokens": 300,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 30,
            "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 10},
        },
    }


def ok_message() -> httpx2.Response:
    return httpx2.Response(200, json=message_json())


def ok_count() -> httpx2.Response:
    return httpx2.Response(200, json={"input_tokens": 4242})


class Harness:
    """A model on a mock transport that replays responses and records sleeps and requests."""

    def __init__(self, responses: Sequence[httpx2.Response], rand: float = 0.5) -> None:
        self.responses = list(responses)
        self.sleeps: list[float] = []
        self.requests: list[httpx2.Request] = []
        self.rand = rand

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.responses[len(self.requests) - 1]

    def factory(self) -> anthropic.AsyncAnthropic:
        transport = httpx2.MockTransport(self.handler)
        return anthropic.AsyncAnthropic(
            api_key=KEY, max_retries=0, http_client=httpx2.AsyncClient(transport=transport)
        )

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def model(self, max_retries: int) -> AnthropicModel:
        return AnthropicModel(
            api_key=SecretStr(KEY),
            model=MODEL_NAME,
            policy=RetryPolicy(max_retries=max_retries, base_seconds=1, cap_seconds=30),
            client_factory=self.factory,
            sleep=self.sleep,
            rand=lambda: self.rand,
        )


def make_request() -> ModelRequest:
    return ModelRequest(
        system="sys",
        tools=(ToolSpec("get_deviations", "Deviations.", {"type": "object", "properties": {}}),),
        messages=(Message("user", (TextBlock("hola"),)),),
        max_tokens=16000,
        effort="medium",
    )


@pytest.mark.parametrize(
    ("statuses", "max_retries", "requests", "sleeps", "failed_status"),
    [
        ([529, 529, 200], 4, 3, [0.75, 1.5], None),
        ([400, 200], 4, 1, [], 400),
        ([529] * 5, 4, 5, [0.75, 1.5, 3.0, 6.0], 529),
    ],
)
async def test_e10_create_retries_retryable_statuses_only(
    statuses: list[int],
    max_retries: int,
    requests: int,
    sleeps: list[float],
    failed_status: int | None,
) -> None:
    """E10 (a)(b)(c): backoff delays, immediate failure on 400, exhaustion names 529, no key leak."""
    responses = [ok_message() if s == 200 else error_response(s) for s in statuses]
    harness = Harness(responses)
    async with harness.model(max_retries).session() as session:
        if failed_status is None:
            reply = await session.create(make_request())
            assert reply.stop_reason == "tool_use"
        else:
            with pytest.raises(ModelCallFailed) as raised:
                await session.create(make_request())
            assert raised.value.status == failed_status
            assert str(failed_status) in str(raised.value)
            assert KEY not in str(raised.value)
            assert raised.value.__context__ is None
            assert raised.value.__cause__ is None
    assert len(harness.requests) == requests
    assert harness.sleeps == sleeps


async def test_e10d_count_tokens_retries_429() -> None:
    """E10 (d): 'count_tokens' retries a 429 once and returns the count."""
    harness = Harness([error_response(429), ok_count()])
    async with harness.model(4).session() as session:
        assert await session.count_tokens(make_request()) == 4242
    assert harness.sleeps == [0.75]


async def test_e10e_wait_is_capped() -> None:
    """E10 (e): with 7 x 529 and 6 retries the 6th sleep is the cap, 30 x 0.75."""
    harness = Harness([error_response(529)] * 7)
    async with harness.model(6).session() as session:
        with pytest.raises(ModelCallFailed):
            await session.create(make_request())
    assert len(harness.requests) == 7
    assert harness.sleeps[5] == 22.5


def test_e11_params_keys_and_block_round_trip() -> None:
    """E11: exact param keys, no sampling params, thinking blocks identical after a round trip."""
    reply = from_message(anthropic.types.Message.model_validate(message_json()))
    assistant = Message("assistant", reply.content)
    results = Message("user", (ToolResultBlock("tu-1", "[]", False),))
    request = ModelRequest(
        system="sys",
        tools=make_request().tools,
        messages=(*make_request().messages, assistant, results),
        max_tokens=16000,
        effort="medium",
    )
    params: dict[str, Any] = to_params(request, MODEL_NAME)
    assert set(params) == {
        "model",
        "max_tokens",
        "system",
        "tools",
        "messages",
        "thinking",
        "output_config",
        "tool_choice",
    }
    assert params["model"] == MODEL_NAME
    assert params["max_tokens"] == 16000
    assert params["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert params["output_config"] == {"effort": "medium"}
    assert params["tool_choice"] == {"type": "auto"}
    assert reply.content == (
        ThinkingBlock("Busco desvíos.", "sig-1"),
        RedactedThinkingBlock("opaque-1"),
        ToolUseBlock("tu-1", "get_deviations", {"a": 1}),
    )
    assert params["messages"][1]["content"] == [
        {"type": "thinking", "thinking": "Busco desvíos.", "signature": "sig-1"},
        {"type": "redacted_thinking", "data": "opaque-1"},
        {"type": "tool_use", "id": "tu-1", "name": "get_deviations", "input": {"a": 1}},
    ]
    assert reply.usage == Usage(
        input_tokens=1200,
        output_tokens=300,
        cache_read_tokens=50,
        cache_write_5m_tokens=20,
        cache_write_1h_tokens=10,
    )


async def test_count_tokens_body_omits_max_tokens_and_output_config() -> None:
    """Risk: the SDK's 'count_tokens' rejects 'max_tokens' and 'output_config', so every count would fail."""
    harness = Harness([ok_count()])
    async with harness.model(0).session() as session:
        await session.count_tokens(make_request())
    body: dict[str, Any] = json.loads(harness.requests[0].content)
    assert harness.requests[0].url.path.endswith("/count_tokens")
    assert "max_tokens" not in body
    assert "output_config" not in body
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"}


def test_r5_unknown_content_block_raises_instead_of_being_dropped() -> None:
    """R5: a block type the port does not know raises 'ValueError' naming it."""
    body = message_json()
    body["content"] = [{"type": "server_tool_use", "id": "s-1", "name": "web_search", "input": {}}]
    message = anthropic.types.Message.model_validate(body)
    with pytest.raises(ValueError, match="server_tool_use"):
        from_message(message)


def test_writes_without_cache_creation_split_count_as_5m() -> None:
    """Risk: a reply with no 'cache_creation' split would drop cache writes from cost."""
    usage: dict[str, object] = {
        "input_tokens": 100,
        "output_tokens": 5,
        "cache_creation_input_tokens": 7,
    }
    reply = from_message(anthropic.types.Message.model_validate(message_json(usage)))
    assert reply.usage.cache_write_5m_tokens == 7
    assert reply.usage.cache_write_1h_tokens == 0
