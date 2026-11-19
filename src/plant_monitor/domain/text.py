"""Text helpers shared by the trace and HTML renderers."""

import re
from typing import Final

_CONTROLS: Final = re.compile("[\x00-\x1f\x7f-\x9f]")


def escape_controls(text: str) -> str:
    """Each C0, DEL and C1 control character becomes '\\xHH'."""
    return _CONTROLS.sub(lambda match: f"\\x{ord(match.group()):02x}", text)
