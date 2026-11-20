"""Shared read-only access to the registry file, in one transaction (013 R2, 014 I3)."""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Final

READ_TIMEOUT_S: Final = 2.0


@contextmanager
def open_readonly(path: Path, *, timeout: float = READ_TIMEOUT_S) -> Iterator[sqlite3.Connection]:
    """Read-only connection inside 'BEGIN'; commits on success, rolls back on any error."""
    if not path.is_file():
        raise ValueError(f"{path}: registry not found")
    with closing(
        sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, autocommit=True, timeout=timeout)
    ) as conn:
        conn.execute("BEGIN")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def check_columns(
    conn: sqlite3.Connection,
    path: Path,
    required: Mapping[str, frozenset[str]],
    *,
    lacks_when_missing: bool = False,
) -> None:
    """Every table and column in 'required' must exist; a missing table may read as 'lacks'."""
    for table, needed in required.items():
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not columns and not lacks_when_missing:
            raise ValueError(f"{path}: table {table} not found")
        if missing := needed - columns:
            raise ValueError(f"{path}: table {table} lacks {sorted(missing)}")
