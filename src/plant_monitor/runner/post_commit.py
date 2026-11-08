"""Post-commit steps run in order; a failing step never blocks the next one."""

import logging
from collections.abc import Sequence

from plant_monitor.runner.ports import PostCommit

logger = logging.getLogger(__name__)


class PostCommitChain:
    """Runs every step's 'after_commit', logging each failure at ERROR."""

    def __init__(self, steps: Sequence[PostCommit]) -> None:
        self._steps = tuple(steps)

    def after_commit(self) -> None:
        for step in self._steps:
            try:
                step.after_commit()
            except Exception:
                logger.exception("post-commit step %s failed", type(step).__name__)
