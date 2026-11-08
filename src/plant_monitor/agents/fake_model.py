"""Scripted model double that records every request and token count."""

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager

from plant_monitor.agents.model import ModelReply, ModelRequest, ModelSession

DEFAULT_COUNT = 3000


class ScriptExhausted(AssertionError):
    """The loop asked for more replies than the script holds."""


class FakeModel:
    """Pops scripted replies (or raises scripted exceptions); doubles as its own session."""

    def __init__(
        self,
        script: Sequence[ModelReply | Exception],
        count: int | Callable[[ModelRequest], int] = DEFAULT_COUNT,
    ) -> None:
        self._script = list(script)
        self._count = count
        self.requests: list[ModelRequest] = []
        self.counted: list[ModelRequest] = []

    async def count_tokens(self, request: ModelRequest) -> int:
        self.counted.append(request)
        return self._count(request) if callable(self._count) else self._count

    async def create(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        if not self._script:
            raise ScriptExhausted("the model script has no more replies")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ModelSession]:
        yield self
