"""Contract tests for Cognitive Engine (CE.1-r3).

These tests define expected behavior BEFORE the Engine is implemented.
They use strict xfail so that:
  - NotImplementedError is expected now,
  - any other failure (AttributeError, bad fixture) is a real FAIL,
  - when Engine is implemented, tests XPASS(strict) and must drop xfail.
"""

import pytest

from igl_cognitive.engine import Engine
from igl_cognitive.frame import CognitiveFrame
from igl_cognitive.rules import Rule
from igl_cognitive.trace import DecisionTrace


XFAIL = pytest.mark.xfail(
    strict=True,
    raises=NotImplementedError,
    reason="CE.1 Engine.select not implemented",
)


# --- helpers ---

def hard_math_verification() -> Rule:
    return Rule(
        id="EXPLICIT_MATH_VERIFICATION",
        priority="HARD",
        condition="explicit_math_verification",
        frame={
            "register": "verification",
            "coordinate_system": "mathematics",
            "strategy": "formal_verification",
        },
        scope="math_request",
        weight=None,
        min_model_tier="strong",
    )


def hard_conversation() -> Rule:
    return Rule(
        id="FORCE_CONVERSATION",
        priority="HARD",
        condition="force_conversation",
        frame={
            "register": "conversation",
            "coordinate_system": "none",
            "strategy": "conceptual_exploration",
        },
        scope="conversation",
        weight=None,
        min_model_tier="small",
    )


def hard_register_verification() -> Rule:
    return Rule(
        id="HARD_VERIFICATION_REGISTER",
        priority="HARD",
        condition="hard_verification_register",
        frame={"register": "verification"},
        scope="verification",
        weight=None,
    )


def hard_strategy_conceptual() -> Rule:
    return Rule(
        id="HARD_CONCEPTUAL_STRATEGY",
        priority="HARD",
        condition="hard_conceptual_strategy",
        frame={"strategy": "conceptual_exploration"},
        scope="conceptual",
        weight=None,
    )


def classifier_philosophy() -> CognitiveFrame:
    return CognitiveFrame(
        register="hypothesis",
        coordinate_system="philosophy",
        strategy="conceptual_exploration",
        model_tier="medium",
        revision=0,
    )


# --- T1: HARD vs classifier -> SELECTED, hard_unique ---

def test_t1_hard_vs_classifier():
    """HARD requires math verification; classifier proposes philosophy.

    Expected:
      event = frame_selection
      resolution = hard_unique
      conflict = True
      conflict_reason = hard_vs_classifier
      selected_frame is the HARD-required frame
    """
    engine = Engine(rules=[hard_math_verification()])
    context = {"explicit_math_verification": True}

    trace = engine.select(
        context=context,
        classifier_proposal=classifier_philosophy(),
        previous_frame=None,
    )

    assert isinstance(trace, DecisionTrace)
    assert trace.event == "frame_selection"
    assert trace.resolution == "hard_unique"
    assert trace.conflict is True
    assert trace.conflict_reason == "hard_vs_classifier"
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "verification"
    assert trace.selected_frame["coordinate_system"] == "mathematics"
    assert trace.selected_frame["strategy"] == "formal_verification"
    assert trace.selected_frame["model_tier"] == "strong"


# --- T3: two incompatible HARD -> FRAME_CONFLICT ---

def test_t3_two_incompatible_hard():
    """Two HARD rules require incompatible frames.

    Expected:
      event = frame_conflict
      selected_frame = None
      conflict_reason = hard_vs_hard
      resolution = none
    """
    engine = Engine(rules=[hard_math_verification(), hard_conversation()])
    context = {
        "explicit_math_verification": True,
        "force_conversation": True,
    }

    trace = engine.select(context=context, classifier_proposal=None, previous_frame=None)

    assert isinstance(trace, DecisionTrace)
    assert trace.event == "frame_conflict"
    assert trace.selected_frame is None
    assert trace.conflict_reason == "hard_vs_hard"
    assert trace.resolution == "none"


# --- T13: HARD rules have no direct field conflict, but no valid frame exists ---

def test_t13_hidden_hard_incompatibility():
    """HARD A requires register=verification; HARD B requires strategy=conceptual_exploration.

    No triple in VALID_FRAMES has (verification, *, conceptual_exploration).
    Fields don't directly contradict, but the registry has no valid frame.

    Expected: same as T3 — FRAME_CONFLICT with hard_vs_hard.
    """
    engine = Engine(rules=[hard_register_verification(), hard_strategy_conceptual()])
    context = {
        "hard_verification_register": True,
        "hard_conceptual_strategy": True,
    }

    trace = engine.select(context=context, classifier_proposal=None, previous_frame=None)

    assert isinstance(trace, DecisionTrace)
    assert trace.event == "frame_conflict"
    assert trace.selected_frame is None
    assert trace.conflict_reason == "hard_vs_hard"
    assert trace.resolution == "none"


# --- T4: two HARD with min_model_tier, combined to strictest ---

def hard_math_strong() -> Rule:
    return Rule(
        id="HARD_MATH_STRONG",
        priority="HARD",
        condition="hard_math_strong",
        frame={
            "register": "verification",
            "coordinate_system": "mathematics",
        },
        scope="math",
        weight=None,
        min_model_tier="strong",
    )


def hard_math_medium() -> Rule:
    return Rule(
        id="HARD_MATH_MEDIUM",
        priority="HARD",
        condition="hard_math_medium",
        frame={
            "register": "verification",
            "coordinate_system": "mathematics",
        },
        scope="math",
        weight=None,
        min_model_tier="medium",
    )


def test_t4_two_hard_min_tier_combined_to_strictest():
    """T4: two HARD rules with min_model_tier strong and medium.

    Expected:
      SELECTED
      register = verification
      coordinate_system = mathematics
      strategy = formal_verification
      model_tier = strong       (max of lower bounds)
      resolution = hard_unique
    """
    engine = Engine(rules=[hard_math_strong(), hard_math_medium()])
    context = {
        "hard_math_strong": True,
        "hard_math_medium": True,
    }

    trace = engine.select(context=context, classifier_proposal=None, previous_frame=None)

    assert trace.event == "frame_selection"
    assert trace.resolution == "hard_unique"
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "verification"
    assert trace.selected_frame["coordinate_system"] == "mathematics"
    assert trace.selected_frame["strategy"] == "formal_verification"
    assert trace.selected_frame["model_tier"] == "strong"


# --- T17: classifier proposes tier below min_model_tier ---

def test_t17_classifier_tier_below_min_rejected():
    """T17: HARD requires min_model_tier=strong. Classifier proposes small.

    Expected:
      SELECTED
      model_tier = strong       (from ALLOWED, not from classifier)
      conflict = True
      conflict_reason = hard_vs_classifier
      resolution = hard_unique

    The classifier's proposal must NOT be silently upgraded.
    It must be recorded as a rejected proposal.
    """
    engine = Engine(rules=[hard_math_strong()])
    context = {"hard_math_strong": True}

    classifier = CognitiveFrame(
        register="verification",
        coordinate_system="mathematics",
        strategy="formal_verification",
        model_tier="small",
        revision=0,
    )

    trace = engine.select(
        context=context,
        classifier_proposal=classifier,
        previous_frame=None,
    )

    assert trace.event == "frame_selection"
    assert trace.resolution == "hard_unique"
    assert trace.selected_frame is not None
    assert trace.selected_frame["model_tier"] == "strong"
    assert trace.conflict is True
    assert trace.conflict_reason == "hard_vs_classifier"

    # The classifier proposal is recorded as-is, not rewritten
    assert trace.classifier is not None
    assert trace.classifier["proposal"]["model_tier"] == "small"


# --- T8: revision does not grow when configuration is unchanged ---

def test_t8_revision_unchanged_when_same_config():
    """T8: previous_frame == selected config; revision must stay the same.

    previous_frame: verification/mathematics/formal_verification/strong, revision=1
    HARD requires the same config.
    Expected: selected revision = 1 (not 2).
    """
    engine = Engine(rules=[hard_math_strong()])
    context = {"hard_math_strong": True}

    previous = CognitiveFrame(
        register="verification",
        coordinate_system="mathematics",
        strategy="formal_verification",
        model_tier="strong",
        revision=1,
    )

    trace = engine.select(context=context, classifier_proposal=None, previous_frame=previous)

    assert trace.event == "frame_selection"
    assert trace.resolution == "hard_unique"
    assert trace.selected_frame is not None
    assert trace.selected_frame["revision"] == 1
    assert trace.revision == 1


# --- T9: revision grows when configuration changes ---

def test_t9_revision_grows_on_config_change():
    """T9: previous_frame config differs; revision increments by 1.

    previous_frame: hypothesis/philosophy/conceptual_exploration/medium, revision=0
    HARD requires verification/mathematics/formal_verification/strong.
    Expected: selected revision = 1.
    """
    engine = Engine(rules=[hard_math_strong()])
    context = {"hard_math_strong": True}

    previous = CognitiveFrame(
        register="hypothesis",
        coordinate_system="philosophy",
        strategy="conceptual_exploration",
        model_tier="medium",
        revision=0,
    )

    trace = engine.select(context=context, classifier_proposal=None, previous_frame=previous)

    assert trace.event == "frame_selection"
    assert trace.selected_frame is not None
    assert trace.selected_frame["revision"] == 1
    assert trace.revision == 1


# --- T3/T13 revisited: conflict does not grow revision ---

def test_t3_conflict_does_not_grow_revision():
    """Conflict: previous_frame revision unchanged; selected_frame is None."""
    engine = Engine(rules=[hard_math_verification(), hard_conversation()])
    context = {
        "explicit_math_verification": True,
        "force_conversation": True,
    }
    previous = CognitiveFrame(
        register="conversation",
        coordinate_system="none",
        strategy="conceptual_exploration",
        model_tier="small",
        revision=5,
    )

    trace = engine.select(context=context, classifier_proposal=None, previous_frame=previous)

    assert trace.event == "frame_conflict"
    assert trace.selected_frame is None
    # revision field in trace mirrors previous.revision when no new frame selected
    assert trace.revision == 5


# --- SOFT helpers ---

def soft_keep_hypothesis() -> Rule:
    """SOFT: prefer register=hypothesis, weight=2."""
    return Rule(
        id="SOFT_KEEP_HYPOTHESIS",
        priority="SOFT",
        condition="soft_keep_hypothesis",
        frame={"register": "hypothesis"},
        scope="continuation",
        weight=2,
        min_model_tier=None,
    )


def soft_keep_philosophy() -> Rule:
    """SOFT: prefer coordinate_system=philosophy, weight=1."""
    return Rule(
        id="SOFT_KEEP_PHILOSOPHY",
        priority="SOFT",
        condition="soft_keep_philosophy",
        frame={"coordinate_system": "philosophy"},
        scope="continuation",
        weight=1,
        min_model_tier=None,
    )


def soft_prefer_memory() -> Rule:
    """SOFT: prefer register=memory, weight=5."""
    return Rule(
        id="SOFT_PREFER_MEMORY",
        priority="SOFT",
        condition="soft_prefer_memory",
        frame={"register": "memory"},
        scope="recall",
        weight=5,
        min_model_tier=None,
    )


def classifier_hypothesis_philosophy() -> CognitiveFrame:
    return CognitiveFrame(
        register="hypothesis",
        coordinate_system="philosophy",
        strategy="conceptual_exploration",
        model_tier="medium",
        revision=0,
    )


def classifier_memory() -> CognitiveFrame:
    return CognitiveFrame(
        register="memory",
        coordinate_system="none",
        strategy="recall",
        model_tier="small",
        revision=0,
    )


# --- T5a: SOFT and classifier agree -> classifier_accepted ---

def test_t5a_soft_and_classifier_agree():
    """T5a: classifier proposes a frame inside ALLOWED that also matches SOFT.

    Expected:
      SELECTED
      resolution = classifier_accepted
      conflict = False
    """
    engine = Engine(rules=[soft_keep_hypothesis(), soft_keep_philosophy()])
    context = {
        "soft_keep_hypothesis": True,
        "soft_keep_philosophy": True,
    }

    trace = engine.select(
        context=context,
        classifier_proposal=classifier_hypothesis_philosophy(),
        previous_frame=None,
    )

    assert trace.event == "frame_selection"
    assert trace.resolution == "classifier_accepted"
    assert trace.conflict is False
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "hypothesis"
    assert trace.selected_frame["coordinate_system"] == "philosophy"


# --- T5b: SOFT and classifier disagree, classifier valid inside ALLOWED ---

def test_t5b_soft_and_classifier_disagree():
    """T5b: SOFT prefers hypothesis, but classifier proposes memory (valid inside ALLOWED).

    SOFT is ranking, not restriction. Classifier wins.

    Expected:
      SELECTED
      resolution = classifier_accepted
      selected = memory/none/recall
    """
    engine = Engine(rules=[soft_keep_hypothesis(), soft_prefer_memory()])
    context = {
        "soft_keep_hypothesis": True,
        "soft_prefer_memory": True,
    }

    trace = engine.select(
        context=context,
        classifier_proposal=classifier_memory(),
        previous_frame=None,
    )

    assert trace.event == "frame_selection"
    assert trace.resolution == "classifier_accepted"
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "memory"
    assert trace.selected_frame["coordinate_system"] == "none"
    assert trace.selected_frame["strategy"] == "recall"


# --- T14: classifier valid inside ALLOWED, differs from SOFT ---

def test_t14_classifier_wins_over_soft():
    """T14: SOFT ranks hypothesis above memory; classifier proposes memory.

    Expected: classifier_accepted, selected = memory/none/recall.
    """
    engine = Engine(rules=[soft_keep_hypothesis(), soft_prefer_memory()])
    context = {
        "soft_keep_hypothesis": True,
        "soft_prefer_memory": True,
    }

    trace = engine.select(
        context=context,
        classifier_proposal=classifier_memory(),
        previous_frame=None,
    )

    assert trace.event == "frame_selection"
    assert trace.resolution == "classifier_accepted"
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "memory"


# --- T16: SOFT tie, no default, no classifier -> UNDETERMINED ---

def test_t16_soft_tie_no_default_undetermined():
    """T16: two SOFT rules with equal weight prefer different frames;
    no DEFAULT, no classifier.

    Expected:
      UNDETERMINED
      selected_frame = None
      undetermined_reason = soft_tie_no_default
    """
    soft_a = Rule(
        id="SOFT_A",
        priority="SOFT",
        condition="soft_a",
        frame={"register": "hypothesis"},
        scope="s",
        weight=1,
        min_model_tier=None,
    )
    soft_b = Rule(
        id="SOFT_B",
        priority="SOFT",
        condition="soft_b",
        frame={"register": "memory"},
        scope="s",
        weight=1,
        min_model_tier=None,
    )
    engine = Engine(rules=[soft_a, soft_b])
    context = {"soft_a": True, "soft_b": True}

    trace = engine.select(context=context, classifier_proposal=None, previous_frame=None)

    assert trace.event == "frame_undetermined"
    assert trace.selected_frame is None
    assert trace.undetermined_reason == "soft_tie_no_default"


# --- T18: SOFT weight must be positive int (already in is_valid_rule) ---

def test_t18_soft_float_weight_rejected_at_engine_construction():
    """T18: Engine must reject a SOFT rule with float weight at construction."""
    bad_rule = Rule(
        id="BAD",
        priority="SOFT",
        condition="bad",
        frame={"register": "memory"},
        scope="s",
        weight=1.5,  # type: ignore[arg-type]
        min_model_tier=None,
    )
    with pytest.raises(ValueError):
        Engine(rules=[bad_rule])


# --- T6: no rules, classifier valid -> classifier_accepted ---

def test_t6_no_rules_classifier_valid():
    """T6: no HARD, no SOFT, classifier proposes a valid frame.

    Expected: classifier_accepted.
    """
    engine = Engine(rules=[])
    context = {}

    trace = engine.select(
        context=context,
        classifier_proposal=classifier_memory(),
        previous_frame=None,
    )

    assert trace.event == "frame_selection"
    assert trace.resolution == "classifier_accepted"
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "memory"


# --- T7: no rules, classifier invalid -> UNDETERMINED ---

def test_t7_no_rules_classifier_invalid():
    """T7: no rules, classifier proposes a frame not in VALID_FRAMES.

    Expected: UNDETERMINED, no selected_frame.
    """
    engine = Engine(rules=[])
    context = {}

    invalid_classifier = CognitiveFrame(
        register="conversation",
        coordinate_system="mathematics",  # not in VALID_FRAMES
        strategy="recall",
        model_tier="small",
        revision=0,
    )

    trace = engine.select(
        context=context,
        classifier_proposal=invalid_classifier,
        previous_frame=None,
    )

    assert trace.event == "frame_undetermined"
    assert trace.selected_frame is None
    assert trace.undetermined_reason is not None


# --- T10: DEFAULT applied when no unique selection ---

def test_t10_default_applied():
    """T10: no HARD/SOFT, classifier rejected, default_frame set and in ALLOWED.

    Expected: SELECTED, resolution=default.
    """
    default = CognitiveFrame(
        register="conversation",
        coordinate_system="none",
        strategy="conceptual_exploration",
        model_tier="small",
        revision=0,
    )
    engine = Engine(rules=[], default_frame=default)
    context = {}

    # Use two SOFTs with equal weight to force a tie, or no classifier + no SOFT
    trace = engine.select(
        context=context,
        classifier_proposal=None,
        previous_frame=None,
    )

    assert trace.event == "frame_selection"
    assert trace.resolution == "default"
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "conversation"
    assert trace.selected_frame["coordinate_system"] == "none"
    assert trace.selected_frame["strategy"] == "conceptual_exploration"


# --- T11: no DEFAULT -> UNDETERMINED ---

def test_t11_no_default_undetermined():
    """T11: no HARD/SOFT, classifier rejected, no default_frame.

    Expected: UNDETERMINED with no_applicable_rule_no_valid_proposal_no_default.
    """
    engine = Engine(rules=[], default_frame=None)
    context = {}

    trace = engine.select(context=context, classifier_proposal=None, previous_frame=None)

    assert trace.event == "frame_undetermined"
    assert trace.selected_frame is None
    assert trace.undetermined_reason == "no_applicable_rule_no_valid_proposal_no_default"