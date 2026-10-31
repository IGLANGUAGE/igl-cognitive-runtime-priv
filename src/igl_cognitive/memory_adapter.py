"""Memory Gate Adapter — contract for CE.2.

Adapter does NOT import IGL internals. It receives a GateResult-like object
(accepted / withheld / constraints) and produces:
  - memory_context: dict[str, Any]  — safe features for Engine rules
  - allowed_memory_ref: str         — canonical hash of the allowed set
  - withheld_diagnostics: list      — for logging, NOT passed to Engine
  - constraints: list               — preserved, NOT passed to Engine rules

The adapter never decides the frame. It only prepares allowed memory.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_payload(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AllowedMemory:
    """Allowed memory, prepared for Cognitive Engine.

    memory_context: safe features (e.g. {"preferred_reasoning": "mathematics"}).
                    Engine uses these as context for its rules.
    allowed_memory_ref: canonical hash of the allowed set (for trace).
    """
    memory_context: dict[str, Any]
    allowed_memory_ref: str


@dataclass(frozen=True)
class MemoryAdapterDiagnostics:
    """Diagnostics — NOT passed to Engine rules.

    withheld_count: how many beliefs Gate withheld.
    withheld_reasons: list of reasons (for logging).
    constraints_count: how many generation constraints Gate returned.
    constraints: preserved list (for downstream, not for rules).
    """
    withheld_count: int
    withheld_reasons: list[str] = field(default_factory=list)
    constraints_count: int = 0
    constraints: list[dict[str, Any]] = field(default_factory=list)


def _extract_feature(belief: dict[str, Any]) -> tuple[str, Any] | None:
    """Extract (key, value) from an accepted item.

    Supports two shapes:

    1. Mock shape:
        {"content": {"key": "...", "value": ...}}

    2. Real IGL Gate shape:
        {"belief": {"value": {"key": "...", "value": ...}, ...},
         "trusted": bool, "applicable": bool, ...}

    For the real shape, `trusted` and `applicable` must both be True
    (if present) for the item to be used.
    """
    # Real Gate shape: wrapper with belief
    inner = belief.get("belief")
    if isinstance(inner, dict):
        trusted = belief.get("trusted", True)
        applicable = belief.get("applicable", True)
        if not (trusted and applicable):
            return None
        value_obj = inner.get("value")
        if isinstance(value_obj, dict):
            key = value_obj.get("key")
            if isinstance(key, str):
                return key, value_obj.get("value")
        return None

    # Mock shape: content
    content = belief.get("content")
    if isinstance(content, dict):
        key = content.get("key")
        if isinstance(key, str):
            return key, content.get("value")
        return None

    return None


def build_allowed_memory(gate_result: dict[str, Any]) -> tuple[AllowedMemory, MemoryAdapterDiagnostics]:
    """Build allowed memory from a GateResult-like dict.

    gate_result must have keys: accepted, withheld, constraints.
    Only `accepted` contributes to memory_context.
    `withheld` and `constraints` go to diagnostics, NOT to Engine.
    """
    accepted = gate_result.get("accepted", []) or []
    withheld = gate_result.get("withheld", []) or []
    constraints = gate_result.get("constraints", []) or []

    memory_context: dict[str, Any] = {}
    allowed_items: list[tuple[str, Any]] = []

    for belief in accepted:
        if not isinstance(belief, dict):
            continue
        pair = _extract_feature(belief)
        if pair is None:
            continue
        key, value = pair
        memory_context[key] = value
        allowed_items.append((key, value))

    # Canonical ref: hash of sorted allowed items
    sorted_items = sorted(allowed_items, key=lambda kv: kv[0])
    allowed_memory_ref = _hash_payload({
        "accepted": sorted_items,
    })

    withheld_reasons = [
        w.get("reason", "unknown") for w in withheld if isinstance(w, dict)
    ]

    allowed = AllowedMemory(
        memory_context=memory_context,
        allowed_memory_ref=allowed_memory_ref,
    )
    diagnostics = MemoryAdapterDiagnostics(
        withheld_count=len(withheld),
        withheld_reasons=withheld_reasons,
        constraints_count=len(constraints),
        constraints=[dict(c) for c in constraints if isinstance(c, dict)],
    )
    return allowed, diagnostics