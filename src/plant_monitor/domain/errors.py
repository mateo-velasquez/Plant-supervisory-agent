"""Base error for refusals whose message is safe to show the model (R13)."""


class RejectedRequest(Exception):
    """A refused request; 'str(error)' is the message the model sees, without any SDK prefix."""
