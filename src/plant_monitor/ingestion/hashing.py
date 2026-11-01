"""Content hash of raw snapshot bytes, used for idempotency."""

import hashlib


def content_hash(data: bytes) -> str:
    """Lowercase hex SHA-256 of the raw bytes."""
    return hashlib.sha256(data).hexdigest()
