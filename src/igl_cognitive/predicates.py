"""Predicate registry for CE.3.

A predicate is a pure function: same context -> same result.
No I/O, no LLM, no time, no randomness.

Registry is immutable after construction: Engine takes a private copy.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Callable, Mapping


Predicate = Callable[[dict], bool]

PREDICATE_PREFIX = "predicate:"
FLAG_PREFIX = "flag:"
MEMORY_PREFIX = "memory:"


def _canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class PredicateRegistry:
    """Immutable registry of named predicates.

    Each entry: name -> (version, callable).
    Name is the bare name without the 'predicate:' prefix.

    The registry makes a private copy of the input mapping.
    No public method mutates the registry after construction.
    """

    def __init__(self, predicates: Mapping[str, tuple[str, Predicate]]) -> None:
        # Private copy, immutable view
        self._entries: Mapping[str, tuple[str, Predicate]] = MappingProxyType(
            {k: (v[0], v[1]) for k, v in predicates.items()}
        )

    def has(self, name: str) -> bool:
        return name in self._entries

    def get(self, name: str) -> tuple[str, Predicate]:
        if name not in self._entries:
            raise KeyError(f"Unknown predicate: {name!r}")
        return self._entries[name]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries.keys()))

    def hash(self) -> str:
        """Canonical hash of {name: version}. Order-independent.

        Note: this hashes names and versions, not function bodies.
        For CE.3 it is a contract of trusted configuration.
        """
        payload = {name: version for name, (version, _) in self._entries.items()}
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def split_condition(condition: str) -> tuple[str, str]:
    """Split a rule condition into (namespace, name).

    Supported:
      'predicate:foo' -> ('predicate', 'foo')
      'flag:foo'      -> ('flag', 'foo')
      'memory:foo'    -> ('memory', 'foo')
      'foo'           -> ('legacy', 'foo')  -- CE.1/CE.2 flat flag
    """
    if condition.startswith(PREDICATE_PREFIX):
        return "predicate", condition[len(PREDICATE_PREFIX):]
    if condition.startswith(FLAG_PREFIX):
        return "flag", condition[len(FLAG_PREFIX):]
    if condition.startswith(MEMORY_PREFIX):
        return "memory", condition[len(MEMORY_PREFIX):]
    # Legacy memory form (CE.2.1b): "memory.<key>" without colon
    if condition.startswith("memory."):
        return "memory", condition[len("memory."):]
    return "legacy", condition