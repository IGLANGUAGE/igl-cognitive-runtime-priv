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