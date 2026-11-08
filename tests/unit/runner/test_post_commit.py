import logging

import pytest

from plant_monitor.runner.post_commit import PostCommitChain


class _Step:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def after_commit(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


def test_e18b_failing_step_is_logged_and_the_next_step_still_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """E18b: one ERROR log for the failing step; the outbox step still runs."""
    trace, outbox = _Step(RuntimeError("disk full")), _Step()
    with caplog.at_level(logging.ERROR):
        PostCommitChain([trace, outbox]).after_commit()
    assert (trace.calls, outbox.calls) == (1, 1)
    assert [r.levelno for r in caplog.records] == [logging.ERROR]
