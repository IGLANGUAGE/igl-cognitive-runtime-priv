"""Cognitive Engine — deterministic CognitiveFrame selection (CE.1-r3).

First implementation stage: HARD rules only.
Covers contract tests T1, T3, T13.

Not yet implemented (later stages):
  - SOFT ranking
  - classifier acceptance inside ALLOWED
  - DEFAULT_SAFE_FRAME
  - revision increments
  - min_model_tier combination beyond simple max
  - T4, T5a/b, T6, T7, T8, T9, T10, T11, T12, T14, T15, T16, T17, T18

Engine does NOT call LLM, does NOT access memory, does NOT do I/O.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .frame import (
    CognitiveFrame,
    VALID_FRAMES,
    VALID_TIERS,
    frame_hash,
    frame_registry_hash,
    frames_same_config,
    is_valid_frame,
)
from .rules import Rule, is_valid_rule, ruleset_hash
from .trace import CONTRACT_VERSION, DecisionTrace


_RESERVED_MEMORY_KEY = "memory"


class GateUnavailableError(RuntimeError):
    """Raised when memory adapter cannot obtain Gate context.

    Fail-closed: Engine must NOT proceed with cached/empty memory.
    """


_TIER_RANK: dict[str, int] = {"small": 0, "medium": 1, "strong": 2}


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_payload(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


def _resolve_condition(condition: str, effective_context: dict):
    """Resolve a rule condition against effective_context.

    Supported forms:
      "explicit_math_verification"        -> effective_context["explicit_math_verification"]
      "memory.preferred_reasoning"        -> effective_context["memory"]["preferred_reasoning"]
    Returns the value, or None if missing.
    """
    if condition.startswith("memory."):
        key = condition[len("memory."):]
        mem = effective_context.get("memory", {})
        if isinstance(mem, dict):
            return mem.get(key)
        return None
    return effective_context.get(condition)


def _is_rule_applicable(rule: Rule, effective_context: dict) -> bool:
    """Rule applies iff resolved condition is True."""
    return _resolve_condition(rule.condition, effective_context) is True


def _triple_satisfies(
    triple: tuple[str, str, str],
    partial_frame: dict[str, str],
) -> bool:
    """Does the (register, coordinate_system, strategy) triple satisfy the partial frame?"""
    register, coord, strategy = triple
    value_by_field = {
        "register": register,
        "coordinate_system": coord,
        "strategy": strategy,
    }
    for field, expected in partial_frame.items():
        if field in value_by_field and value_by_field[field] != expected:
            return False
    return True


def _tier_satisfies(tier: str, min_tier: str | None) -> bool:
    if min_tier is None:
        return True
    return _TIER_RANK.get(tier, -1) >= _TIER_RANK.get(min_tier, 999)


def _frame_satisfies_soft(
    register: str,
    coord: str,
    strategy: str,
    partial_frame: dict[str, str],
) -> bool:
    """Does the full frame satisfy the SOFT rule's partial frame?"""
    value_by_field = {
        "register": register,
        "coordinate_system": coord,
        "strategy": strategy,
    }
    for field, expected in partial_frame.items():
        if field in value_by_field and value_by_field[field] != expected:
            return False
    return True


def _classifier_matches_allowed(
    classifier: CognitiveFrame,
    allowed: list[tuple[str, str, str, str]],
) -> tuple[str, str, str, str] | None:
    """If classifier (triple + tier) is inside ALLOWED, return that allowed entry."""
    if classifier.model_tier not in VALID_TIERS:
        return None
    target = (
        classifier.register,
        classifier.coordinate_system,
        classifier.strategy,
        classifier.model_tier,
    )
    for entry in allowed:
        if entry == target:
            return entry
    return None


class Engine:
    """Deterministic cognitive frame selector (HARD-only stage)."""

    def __init__(
        self,
        rules: list[Rule],
        default_frame: CognitiveFrame | None = None,
    ) -> None:
        for rule in rules:
            if not is_valid_rule(rule):
                raise ValueError(f"Invalid rule: {rule.id!r}")
        if default_frame is not None and not is_valid_frame(default_frame):
            raise ValueError("Invalid default_frame")

        self.rules = list(rules)
        self.default_frame = default_frame

    # --- ALLOWED computation ---

    def _applicable_hard(self, context: dict) -> list[Rule]:
        return [
            r for r in self.rules
            if r.priority == "HARD" and _is_rule_applicable(r, context)
        ]

    def _allowed_frames(self, hard_rules: list[Rule]) -> list[tuple[str, str, str, str]]:
        """Return list of (register, coord, strategy, tier) allowed by all HARD rules."""
        # Combined min tier from applicable HARD rules
        combined_min: str | None = None
        for r in hard_rules:
            if r.min_model_tier is not None:
                if combined_min is None or _TIER_RANK[r.min_model_tier] > _TIER_RANK[combined_min]:
                    combined_min = r.min_model_tier

        allowed: list[tuple[str, str, str, str]] = []
        for triple in sorted(VALID_FRAMES):
            if not all(_triple_satisfies(triple, r.frame) for r in hard_rules):
                continue
            for tier in sorted(VALID_TIERS, key=lambda t: _TIER_RANK[t]):
                if _tier_satisfies(tier, combined_min):
                    allowed.append((triple[0], triple[1], triple[2], tier))
        return allowed

    # --- select ---

    def select(
        self,
        context: dict,
        classifier_proposal: CognitiveFrame | None = None,
        previous_frame: CognitiveFrame | None = None,
        memory_context: dict | None = None,
        allowed_memory_ref: str | None = None,
        gate_available: bool = True,
    ) -> DecisionTrace:
        # Fail-closed: if Gate unavailable, refuse to proceed.
        if not gate_available:
            raise GateUnavailableError(
                "Gate context unavailable; refusing to select frame with cached memory"
            )

        # Reserved key check: user context must not contain "memory".
        if _RESERVED_MEMORY_KEY in context:
            raise ValueError(
                f"Reserved key {_RESERVED_MEMORY_KEY!r} in user context"
            )

        # Build effective context: user context + memory namespace.
        effective_context: dict = dict(context)
        effective_context[_RESERVED_MEMORY_KEY] = dict(memory_context or {})
        
        # All rule conditions see effective_context.
        # Memory-conditioned rules use condition path "memory.preferred_reasoning"
        # through a dedicated resolver below.
        hard_rules = self._applicable_hard(effective_context)
        
        allowed = self._allowed_frames(hard_rules)
        target_revision = previous_frame.revision if previous_frame is not None else 0

        # Hashes for trace
        ruleset_h = ruleset_hash(self.rules)
        registry_h = frame_registry_hash()
        input_h = _hash_payload({"context": context})
        context_h = _hash_payload({
            "user_context": context,
            "memory_context": memory_context or {},
        })
        state_h = _hash_payload({
            "previous_frame": (
                frame_hash(previous_frame) if previous_frame is not None else None
            )
        })
        allowed_h = _hash_payload({"allowed": allowed})

        rules_fired = [
            {"id": r.id, "priority": r.priority, "weight": r.weight}
            for r in hard_rules
        ]

        # --- FRAME_CONFLICT: no allowed frames ---
        if not allowed:
            return DecisionTrace(
                event="frame_conflict",
                ruleset_hash=ruleset_h,
                frame_registry_hash=registry_h,
                input_hash=input_h,
                context_hash=context_h,
                state_hash=state_h,
                allowed_frames_hash=allowed_h,
                allowed_memory_ref=allowed_memory_ref,
                rules_fired=rules_fired,
                classifier=None,
                conflict=True,
                conflict_reason="hard_vs_hard",
                resolution="none",
                previous_frame=(
                    {
                        "register": previous_frame.register,
                        "coordinate_system": previous_frame.coordinate_system,
                        "strategy": previous_frame.strategy,
                        "model_tier": previous_frame.model_tier,
                        "revision": previous_frame.revision,
                    }
                    if previous_frame is not None
                    else None
                ),
                selected_frame=None,
                revision=target_revision,
                undetermined_reason=None,
            )

        # --- hard_unique: exactly one allowed frame ---
        if len(allowed) == 1:
            reg, coord, strat, tier = allowed[0]
            candidate = CognitiveFrame(
                register=reg,
                coordinate_system=coord,
                strategy=strat,
                model_tier=tier,
                revision=target_revision,
            )

            if previous_frame is not None and not frames_same_config(candidate, previous_frame):
                new_revision = previous_frame.revision + 1
            else:
                new_revision = target_revision

            selected = CognitiveFrame(
                register=reg,
                coordinate_system=coord,
                strategy=strat,
                model_tier=tier,
                revision=new_revision,
            )

            classifier_differs = (
                classifier_proposal is not None
                and not (
                    classifier_proposal.register == reg
                    and classifier_proposal.coordinate_system == coord
                    and classifier_proposal.strategy == strat
                    and classifier_proposal.model_tier == tier
                )
            )
            return DecisionTrace(
                event="frame_selection",
                ruleset_hash=ruleset_h,
                frame_registry_hash=registry_h,
                input_hash=input_h,
                context_hash=context_h,
                state_hash=state_h,
                allowed_frames_hash=allowed_h,
                allowed_memory_ref=allowed_memory_ref,
                rules_fired=rules_fired,
                classifier=(
                    {
                        "proposal": {
                            "register": classifier_proposal.register,
                            "coordinate_system": classifier_proposal.coordinate_system,
                            "strategy": classifier_proposal.strategy,
                            "model_tier": classifier_proposal.model_tier,
                        },
                        "version": "stage1",
                        "params_hash": _hash_payload({}),
                    }
                    if classifier_proposal is not None
                    else None
                ),
                conflict=classifier_differs,
                conflict_reason="hard_vs_classifier" if classifier_differs else "none",
                resolution="hard_unique",
                previous_frame=(
                    {
                        "register": previous_frame.register,
                        "coordinate_system": previous_frame.coordinate_system,
                        "strategy": previous_frame.strategy,
                        "model_tier": previous_frame.model_tier,
                        "revision": previous_frame.revision,
                    } 
                    if previous_frame is not None
                    else None
                ),
                selected_frame={
                    "register": reg,
                    "coordinate_system": coord,
                    "strategy": strat,
                    "model_tier": tier,
                    "revision": new_revision,
                },
                revision=new_revision,
                undetermined_reason=None,
            )

                # --- multiple allowed: classifier first, then SOFT ranking ---

        applicable_soft = [
            r for r in self.rules
            if r.priority == "SOFT" and _is_rule_applicable(r, effective_context)
        ]

        rules_fired_soft = [
            {"id": r.id, "priority": r.priority, "weight": r.weight}
            for r in applicable_soft
        ]
        all_rules_fired = rules_fired + rules_fired_soft

        # 1. Classifier acceptance inside ALLOWED
        if classifier_proposal is not None:
            matched = _classifier_matches_allowed(classifier_proposal, allowed)
            if matched is not None:
                reg, coord, strat, tier = matched
                candidate = CognitiveFrame(
                    register=reg, coordinate_system=coord, strategy=strat,
                    model_tier=tier, revision=target_revision,
                )
                if previous_frame is not None and not frames_same_config(candidate, previous_frame):
                    new_revision = previous_frame.revision + 1
                else:
                    new_revision = target_revision
                return DecisionTrace(
                    event="frame_selection",
                    ruleset_hash=ruleset_h,
                    frame_registry_hash=registry_h,
                    input_hash=input_h,
                    context_hash=context_h,
                    state_hash=state_h,
                    allowed_frames_hash=allowed_h,
                    allowed_memory_ref=allowed_memory_ref,
                    rules_fired=all_rules_fired,
                    classifier={
                        "proposal": {
                            "register": classifier_proposal.register,
                            "coordinate_system": classifier_proposal.coordinate_system,
                            "strategy": classifier_proposal.strategy,
                            "model_tier": classifier_proposal.model_tier,
                        },
                        "version": "stage2",
                        "params_hash": _hash_payload({}),
                    },
                    conflict=False,
                    conflict_reason="none",
                    resolution="classifier_accepted",
                    previous_frame=(
                        {
                            "register": previous_frame.register,
                            "coordinate_system": previous_frame.coordinate_system,
                            "strategy": previous_frame.strategy,
                            "model_tier": previous_frame.model_tier,
                            "revision": previous_frame.revision,
                        }
                        if previous_frame is not None
                        else None
                    ),
                    selected_frame={
                        "register": reg,
                        "coordinate_system": coord,
                        "strategy": strat,
                        "model_tier": tier,
                        "revision": new_revision,
                    },
                    revision=new_revision,
                    undetermined_reason=None,
                )

        # 2. SOFT ranking inside ALLOWED
        scored: list[tuple[int, tuple[str, str, str, str]]] = []
        for entry in allowed:
            reg, coord, strat, tier = entry
            score = 0
            for r in applicable_soft:
                if _frame_satisfies_soft(reg, coord, strat, r.frame):
                    score += r.weight  # positive int guaranteed by is_valid_rule
            scored.append((score, entry))

        if not scored:
            # allowed non-empty, but scored empty - shouldn't happen
            max_score = 0
            winners: list[tuple[str, str, str, str]] = []
        else:
            max_score = max(s for s, _ in scored)
            winners = [entry for s, entry in scored if s == max_score]

        # 3. Unique SOFT winner
        if len(winners) == 1:
            reg, coord, strat, tier = winners[0]
            candidate = CognitiveFrame(
                register=reg, coordinate_system=coord, strategy=strat,
                model_tier=tier, revision=target_revision,
            )
            if previous_frame is not None and not frames_same_config(candidate, previous_frame):
                new_revision = previous_frame.revision + 1
            else:
                new_revision = target_revision
            return DecisionTrace(
                event="frame_selection",
                ruleset_hash=ruleset_h,
                frame_registry_hash=registry_h,
                input_hash=input_h,
                context_hash=context_h,
                state_hash=state_h,
                allowed_frames_hash=allowed_h,
                allowed_memory_ref=allowed_memory_ref,
                rules_fired=all_rules_fired,
                classifier=(
                    {
                        "proposal": {
                            "register": classifier_proposal.register,
                            "coordinate_system": classifier_proposal.coordinate_system,
                            "strategy": classifier_proposal.strategy,
                            "model_tier": classifier_proposal.model_tier,
                        },
                        "version": "stage2",
                        "params_hash": _hash_payload({}),
                    }
                    if classifier_proposal is not None
                    else None
                ),
                conflict=False,
                conflict_reason="none",
                resolution="soft_rule_accept",
                previous_frame=(
                    {
                        "register": previous_frame.register,
                        "coordinate_system": previous_frame.coordinate_system,
                        "strategy": previous_frame.strategy,
                        "model_tier": previous_frame.model_tier,
                        "revision": previous_frame.revision,
                    }
                    if previous_frame is not None
                    else None
                ),
                selected_frame={
                    "register": reg,
                    "coordinate_system": coord,
                    "strategy": strat,
                    "model_tier": tier,
                    "revision": new_revision,
                },
                revision=new_revision,
                undetermined_reason=None,
            )

                # 4. DEFAULT, then UNDETERMINED
        if self.default_frame is not None:
            # Is default inside ALLOWED?
            default_entry = (
                self.default_frame.register,
                self.default_frame.coordinate_system,
                self.default_frame.strategy,
                self.default_frame.model_tier,
            )
            if default_entry in allowed:
                reg, coord, strat, tier = default_entry
                candidate = CognitiveFrame(
                    register=reg, coordinate_system=coord, strategy=strat,
                    model_tier=tier, revision=target_revision,
                )
                if previous_frame is not None and not frames_same_config(candidate, previous_frame):
                    new_revision = previous_frame.revision + 1
                else:
                    new_revision = target_revision
                return DecisionTrace(
                    event="frame_selection",
                    ruleset_hash=ruleset_h,
                    frame_registry_hash=registry_h,
                    input_hash=input_h,
                    context_hash=context_h,
                    state_hash=state_h,
                    allowed_frames_hash=allowed_h,
                    allowed_memory_ref=allowed_memory_ref,
                    rules_fired=all_rules_fired,
                    classifier=(
                        {
                            "proposal": {
                                "register": classifier_proposal.register,
                                "coordinate_system": classifier_proposal.coordinate_system,
                                "strategy": classifier_proposal.strategy,
                                "model_tier": classifier_proposal.model_tier,
                            },
                            "version": "stage3",
                            "params_hash": _hash_payload({}),
                        }
                        if classifier_proposal is not None
                        else None
                    ),
                    conflict=False,
                    conflict_reason="none",
                    resolution="default",
                    previous_frame=(
                        {
                            "register": previous_frame.register,
                            "coordinate_system": previous_frame.coordinate_system,
                            "strategy": previous_frame.strategy,
                            "model_tier": previous_frame.model_tier,
                            "revision": previous_frame.revision,
                        }
                        if previous_frame is not None
                        else None
                    ),
                    selected_frame={
                        "register": reg,
                        "coordinate_system": coord,
                        "strategy": strat,
                        "model_tier": tier,
                        "revision": new_revision,
                    },
                    revision=new_revision,
                    undetermined_reason=None,
                )

        # 5. UNDETERMINED: choose reason
        if not hard_rules and not applicable_soft:
            reason = "no_applicable_rule_no_valid_proposal_no_default"
        else:
            reason = "soft_tie_no_default"

        return DecisionTrace(
            event="frame_undetermined",
            ruleset_hash=ruleset_h,
            frame_registry_hash=registry_h,
            input_hash=input_h,
            context_hash=context_h,
            state_hash=state_h,
            allowed_frames_hash=allowed_h,
            allowed_memory_ref=allowed_memory_ref,
            rules_fired=all_rules_fired,
            classifier=None,
            conflict=False,
            conflict_reason="none",
            resolution="none",
            previous_frame=(
                {
                    "register": previous_frame.register,
                    "coordinate_system": previous_frame.coordinate_system,
                    "strategy": previous_frame.strategy,
                    "model_tier": previous_frame.model_tier,
                    "revision": previous_frame.revision,
                }
                if previous_frame is not None
                else None
            ),
            selected_frame=None,
            revision=target_revision,
            undetermined_reason=reason,
        )