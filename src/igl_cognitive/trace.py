"""DecisionTrace — структурированное событие выбора CognitiveFrame (CE.1-r3).

Трейс строится из фактов решения Engine, а не генерируется LLM.
Содержит только хеши и ссылки, без исходного текста, токенов и секретов.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


CONTRACT_VERSION = "CE.1-r3"

VALID_EVENTS: frozenset[str] = frozenset({
    "frame_selection",
    "frame_conflict",
    "frame_undetermined",
})

VALID_RESOLUTIONS: frozenset[str] = frozenset({
    "hard_unique",
    "hard_rule_override",
    "soft_rule_accept",
    "classifier_accepted",
    "default",
    "none",
})

VALID_CONFLICT_REASONS: frozenset[str] = frozenset({
    "hard_vs_classifier",
    "hard_vs_hard",
    "none",
})


@dataclass(frozen=True)
class DecisionTrace:
    """Одно решение Engine.

    Инварианты:
      - event == "frame_selection"  -> selected_frame is not None
      - event == "frame_conflict"   -> selected_frame is None
      - event == "frame_undetermined" -> selected_frame is None, undetermined_reason is not None
    """
    event: str
    ruleset_hash: str
    frame_registry_hash: str
    input_hash: str
    context_hash: str
    state_hash: str
    allowed_frames_hash: str
    rules_fired: list[dict[str, Any]] = field(default_factory=list)
    classifier: dict[str, Any] | None = None
    conflict: bool = False
    conflict_reason: str = "none"
    resolution: str = "none"
    previous_frame: dict[str, Any] | None = None
    selected_frame: dict[str, Any] | None = None
    revision: int = 0
    allowed_memory_ref: str | None = None
    undetermined_reason: str | None = None
    contract_version: str = CONTRACT_VERSION


def is_valid_trace(trace: DecisionTrace) -> bool:
    """Проверка инвариантов трейса (CE.1-r3)."""
    if trace.contract_version != CONTRACT_VERSION:
        return False
    if trace.event not in VALID_EVENTS:
        return False
    if trace.resolution not in VALID_RESOLUTIONS:
        return False
    if trace.conflict_reason not in VALID_CONFLICT_REASONS:
        return False
    if not isinstance(trace.revision, int) or trace.revision < 0:
        return False

    # Инварианты по event
    if trace.event == "frame_selection":
        if trace.selected_frame is None:
            return False
    elif trace.event == "frame_conflict":
        if trace.selected_frame is not None:
            return False
        if trace.conflict_reason != "hard_vs_hard":
            return False
    elif trace.event == "frame_undetermined":
        if trace.selected_frame is not None:
            return False
        if not trace.undetermined_reason:
            return False

    return True


# --- Каноническая сериализация ---

def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def trace_to_dict(trace: DecisionTrace) -> dict[str, Any]:
    return {
        "contract_version": trace.contract_version,
        "event": trace.event,
        "ruleset_hash": trace.ruleset_hash,
        "frame_registry_hash": trace.frame_registry_hash,
        "input_hash": trace.input_hash,
        "context_hash": trace.context_hash,
        "state_hash": trace.state_hash,
        "allowed_frames_hash": trace.allowed_frames_hash,
        "allowed_memory_ref": trace.allowed_memory_ref,
        "rules_fired": [dict(r) for r in trace.rules_fired],
        "classifier": _copy_optional_dict(trace.classifier),
        "conflict": trace.conflict,
        "conflict_reason": trace.conflict_reason,
        "resolution": trace.resolution,
        "previous_frame": _copy_optional_dict(trace.previous_frame),
        "selected_frame": _copy_optional_dict(trace.selected_frame),
        "revision": trace.revision,
        "undetermined_reason": trace.undetermined_reason,
    }


def _copy_optional_dict(d: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(d) if d is not None else None


def trace_from_dict(d: dict[str, Any]) -> DecisionTrace:
    return DecisionTrace(
        event=d["event"],
        ruleset_hash=d["ruleset_hash"],
        frame_registry_hash=d["frame_registry_hash"],
        input_hash=d["input_hash"],
        context_hash=d["context_hash"],
        state_hash=d["state_hash"],
        allowed_frames_hash=d["allowed_frames_hash"],
        rules_fired=[dict(r) for r in d.get("rules_fired", [])],
        classifier=_copy_optional_dict(d.get("classifier")),
        conflict=d.get("conflict", False),
        conflict_reason=d.get("conflict_reason", "none"),
        resolution=d.get("resolution", "none"),
        previous_frame=_copy_optional_dict(d.get("previous_frame")),
        selected_frame=_copy_optional_dict(d.get("selected_frame")),
        revision=d.get("revision", 0),
        allowed_memory_ref=d.get("allowed_memory_ref"),
        undetermined_reason=d.get("undetermined_reason"),
        contract_version=d.get("contract_version", CONTRACT_VERSION),
    )


def trace_hash(trace: DecisionTrace) -> str:
    """Канонический хеш трейса — для проверки детерминизма (T2)."""
    return hashlib.sha256(
        _canonical_json(trace_to_dict(trace)).encode("utf-8")
    ).hexdigest()