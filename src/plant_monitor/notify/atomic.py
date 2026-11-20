"""Atomic file write shared by the file channel and the HTML pages."""

import contextlib
import os
import tempfile
from pathlib import Path


def write_atomic(target: Path, data: bytes) -> None:
    """Atomic write: temp file in the same directory, then 'os.replace'."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
