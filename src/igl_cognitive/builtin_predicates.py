"""Built-in deterministic predicates for CE.3.

No LLM, no I/O. Pure functions: same context -> same result.
These predicates recognise specific predefined language patterns.
They are NOT general natural-language understanding.
"""

from __future__ import annotations

import re
from collections.abc import Callable


# Imperative / request patterns only.
# Mentioning "mathematical proof" is not the same as requesting one.
_MATH_REQUEST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bдокажи(?:те)?\s+математически\b", re.IGNORECASE),
    re.compile(r"\bдоказать\s+математически\b", re.IGNORECASE),
    re.compile(r"\bmathematically\s+prove\b", re.IGNORECASE),
    re.compile(r"\bprove\s+mathematically\b", re.IGNORECASE),
    re.compile(r"\bformally\s+prove\b", re.IGNORECASE),
    re.compile(r"\bprovide\s+a\s+formal\s+proof\b", re.IGNORECASE),
)


def contains_math_request(context: dict) -> bool:
    """True if current allowed text contains an explicit request
    to prove something mathematically.

    This is pattern matching, not semantic understanding.
    """
    text = context.get("text", "")
    if not isinstance(text, str):
        return False
    return any(p.search(text) for p in _MATH_REQUEST_PATTERNS)


BUILTIN_PREDICATES: dict[str, tuple[str, Callable[[dict], bool]]] = {
    "text.contains_math_request": ("1", contains_math_request),
}