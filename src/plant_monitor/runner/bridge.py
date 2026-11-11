"""Bridge from the synchronous runner to an async agent loop inside a snapshot frame (X5)."""

from collections.abc import Awaitable, Callable

import anyio

from plant_monitor.mcp_server.context import FrameHolder, SnapshotFrame


def _single_leaf(error: BaseExceptionGroup[BaseException]) -> BaseException:
    """Descend through groups holding exactly one exception; other groups stay as they are."""
    current: BaseException = error
    while isinstance(current, BaseExceptionGroup) and len(current.exceptions) == 1:
        current = current.exceptions[0]
    return current


def run_in_frame[*Args, T](
    frames: FrameHolder, frame: SnapshotFrame, run: Callable[[*Args], Awaitable[T]], *args: *Args
) -> T:
    """Run 'run' under 'anyio.run' with 'frame' entered; single-exception groups unwrap to the leaf."""
    try:
        with frames.entered(frame):
            return anyio.run(run, *args)
    except BaseExceptionGroup as group:
        leaf = _single_leaf(group)
        if leaf is group:
            raise
        raise leaf from None
