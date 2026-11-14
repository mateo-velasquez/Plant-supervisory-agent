"""010 T1: the hook chain runs first-block-wins for pre and stop, and every hook for post (E1)."""

from plant_monitor.hooks.chain import HookBlock, HookChain, HookContext, ToolCall
from plant_monitor.mcp_server.types import ToolOutcome

CALL = ToolCall("emit_alert", {"case_id": "S001-Sedán-Local"})
CTX = HookContext("coordinator", 1, None)
OUTCOME = ToolOutcome("ok", False)


class FakeHook:
    """Pre and stop hook that returns a fixed reason and records its calls."""

    def __init__(self, name: str, reason: str | None, seen: list[str]) -> None:
        self.name = name
        self._reason = reason
        self._seen = seen

    def check(self, *args: object) -> str | None:
        self._seen.append(self.name)
        return self._reason


class FakePost:
    """Post hook that records its calls."""

    def __init__(self, name: str, seen: list[str]) -> None:
        self.name = name
        self._seen = seen

    def verify(self, call: ToolCall, outcome: ToolOutcome, ctx: HookContext) -> None:
        self._seen.append(self.name)


def test_e1_chain_first_block_wins_and_post_runs_every_hook() -> None:
    """010 E1: pre and stop stop at the first block; post calls all in order; empty chain is silent."""
    seen: list[str] = []
    chain = HookChain(
        pre=(FakeHook("h1", None, seen), FakeHook("h2", "r2", seen), FakeHook("h3", "r3", seen)),
        post=(FakePost("p1", seen), FakePost("p2", seen)),
        stop=(FakeHook("s1", None, seen), FakeHook("s2", "n2", seen)),
    )
    assert chain.pre_tool(CALL, CTX) == HookBlock("h2", "r2")
    assert seen == ["h1", "h2"]
    seen.clear()
    chain.post_tool(CALL, OUTCOME, CTX)
    assert seen == ["p1", "p2"]
    seen.clear()
    assert chain.on_stop("Listo.", CTX) == HookBlock("s2", "n2")
    assert seen == ["s1", "s2"]
    empty = HookChain()
    assert empty.pre_tool(CALL, CTX) is None
    empty.post_tool(CALL, OUTCOME, CTX)
    assert empty.on_stop("t", CTX) is None
