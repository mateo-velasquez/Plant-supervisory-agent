"""Model port: content blocks, request and reply types, session protocols; no SDK."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Literal, Protocol

from plant_monitor.mcp_server.types import ToolSpec
from plant_monitor.telemetry.usage import Usage

type Effort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class ThinkingBlock:
    thinking: str
    signature: str


@dataclass(frozen=True)
class RedactedThinkingBlock:
    data: str


@dataclass(frozen=True)
class ToolUseBlock:
    id: str
    name: str
    input: Mapping[str, object]


@dataclass(frozen=True)
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool


type ContentBlock = TextBlock | ThinkingBlock | RedactedThinkingBlock | ToolUseBlock | ToolResultBlock


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: tuple[ContentBlock, ...]


@dataclass(frozen=True)
class ModelRequest:
    system: str
    tools: tuple[ToolSpec, ...]
    messages: tuple[Message, ...]
    max_tokens: int
    effort: Effort


@dataclass(frozen=True)
class ModelReply:
    content: tuple[ContentBlock, ...]
    stop_reason: str
    usage: Usage


class ModelSession(Protocol):
    """One open conversation channel to the model."""

    async def count_tokens(self, request: ModelRequest) -> int: ...

    async def create(self, request: ModelRequest) -> ModelReply: ...


class ModelPort(Protocol):
    """Opens a 'ModelSession'; the loop enters it once per snapshot."""

    def session(self) -> AbstractAsyncContextManager[ModelSession]: ...


class ModelCallFailed(Exception):
    """A model call failed for good; the message carries no key and no body (R7)."""

    def __init__(self, operation: str, status: int | None) -> None:
        super().__init__(f"model call '{operation}' failed (status {status})")
        self.operation = operation
        self.status = status
