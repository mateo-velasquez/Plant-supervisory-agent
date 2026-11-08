"""Anthropic adapter for the model port: own retries and SDK conversion (the only 'anthropic' import)."""

import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import anthropic
import anyio
from pydantic import SecretStr

from plant_monitor.agents.model import (
    ContentBlock,
    Message,
    ModelCallFailed,
    ModelReply,
    ModelRequest,
    ModelSession,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from plant_monitor.config import Settings
from plant_monitor.telemetry.usage import Usage

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = frozenset({408, 409, 429})
SERVER_ERROR_FROM = 500


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    base_seconds: float
    cap_seconds: float


def backoff_delay(retry: int, policy: RetryPolicy, r: float) -> float:
    """Wait before retry 'retry' (1-based): capped exponential with jitter in [0.5, 1.0]."""
    ceiling = min(policy.cap_seconds, policy.base_seconds * float(2 ** (retry - 1)))
    return float(ceiling * (0.5 + 0.5 * r))


def is_retryable(error: BaseException) -> bool:
    if isinstance(error, anthropic.APIStatusError):
        return error.status_code in RETRYABLE_STATUSES or error.status_code >= SERVER_ERROR_FROM
    return isinstance(error, anthropic.APIConnectionError)


def _block_param(block: ContentBlock) -> dict[str, object]:
    match block:
        case TextBlock():
            return {"type": "text", "text": block.text}
        case ThinkingBlock():
            return {"type": "thinking", "thinking": block.thinking, "signature": block.signature}
        case RedactedThinkingBlock():
            return {"type": "redacted_thinking", "data": block.data}
        case ToolUseBlock():
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": dict(block.input),
            }
        case ToolResultBlock():
            return {
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": block.content,
                "is_error": block.is_error,
            }


def _message_param(message: Message) -> dict[str, object]:
    return {"role": message.role, "content": [_block_param(b) for b in message.content]}


def to_params(request: ModelRequest, model: str) -> dict[str, object]:
    """Keyword arguments for 'messages.create' (E11); no sampling parameters."""
    return {
        "model": model,
        "max_tokens": request.max_tokens,
        "system": request.system,
        "tools": [
            {"name": t.name, "description": t.description, "input_schema": dict(t.input_schema)}
            for t in request.tools
        ],
        "messages": [_message_param(m) for m in request.messages],
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": request.effort},
        "tool_choice": {"type": "auto"},
    }


def _count_params(request: ModelRequest, model: str) -> dict[str, object]:
    params = to_params(request, model)
    del params["max_tokens"], params["output_config"]
    return params


def _usage(usage: anthropic.types.Usage) -> Usage:
    split = usage.cache_creation
    if split is not None:
        write_5m, write_1h = split.ephemeral_5m_input_tokens, split.ephemeral_1h_input_tokens
    else:
        write_5m, write_1h = usage.cache_creation_input_tokens or 0, 0
    return Usage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_input_tokens or 0,
        cache_write_5m_tokens=write_5m,
        cache_write_1h_tokens=write_1h,
    )


def from_message(message: anthropic.types.Message) -> ModelReply:
    """Map an SDK message to the port reply, reading blocks by 'type'."""
    blocks: list[ContentBlock] = []
    for block in message.content:
        if block.type == "text":
            blocks.append(TextBlock(block.text))
        elif block.type == "thinking":
            blocks.append(ThinkingBlock(block.thinking, block.signature))
        elif block.type == "redacted_thinking":
            blocks.append(RedactedThinkingBlock(block.data))
        elif block.type == "tool_use":
            blocks.append(ToolUseBlock(block.id, block.name, dict(block.input)))
        else:
            raise ValueError(f"unsupported content block type {block.type}")
    return ModelReply(
        content=tuple(blocks),
        stop_reason=message.stop_reason or "",
        usage=_usage(message.usage),
    )


class _Session:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        model: str,
        policy: RetryPolicy,
        sleep: Callable[[float], Awaitable[None]],
        rand: Callable[[], float],
    ) -> None:
        self._client = client
        self._model = model
        self._policy = policy
        self._sleep = sleep
        self._rand = rand

    async def _with_retries[T](self, operation: str, call: Callable[[], Awaitable[T]]) -> T:
        retry = 0
        while True:
            try:
                return await call()
            except anthropic.APIError as error:
                status = error.status_code if isinstance(error, anthropic.APIStatusError) else None
                failure: ModelCallFailed | None = None
                if not is_retryable(error) or retry >= self._policy.max_retries:
                    failure = ModelCallFailed(operation, status)
            if failure is not None:
                # raised outside the 'except' so no SDK error (headers, body) stays in '__context__'
                raise failure
            retry += 1
            delay = backoff_delay(retry, self._policy, self._rand())
            logger.warning(
                "model call '%s' retry %d after status %s in %.2fs", operation, retry, status, delay
            )
            await self._sleep(delay)

    async def count_tokens(self, request: ModelRequest) -> int:
        params: dict[str, Any] = _count_params(request, self._model)

        async def call() -> int:
            result = await self._client.messages.count_tokens(**params)
            return result.input_tokens

        return await self._with_retries("count_tokens", call)

    async def create(self, request: ModelRequest) -> ModelReply:
        params: dict[str, Any] = to_params(request, self._model)

        async def call() -> ModelReply:
            return from_message(await self._client.messages.create(**params))

        return await self._with_retries("create", call)


class AnthropicModel:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        policy: RetryPolicy,
        client_factory: Callable[[], anthropic.AsyncAnthropic] | None = None,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._policy = policy
        self._client_factory = client_factory
        self._sleep = sleep
        self._rand = rand

    @classmethod
    def from_settings(cls, settings: Settings) -> AnthropicModel:
        policy = RetryPolicy(
            max_retries=settings.anthropic_max_retries,
            base_seconds=settings.anthropic_retry_base_seconds,
            cap_seconds=settings.anthropic_retry_cap_seconds,
        )
        return cls(api_key=settings.anthropic_api_key, model=settings.anthropic_model, policy=policy)

    def _new_client(self) -> anthropic.AsyncAnthropic:
        if self._client_factory is not None:
            return self._client_factory()
        return anthropic.AsyncAnthropic(api_key=self._api_key.get_secret_value(), max_retries=0)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ModelSession]:
        client = self._new_client()
        try:
            yield _Session(client, self._model, self._policy, self._sleep, self._rand)
        finally:
            await client.close()
