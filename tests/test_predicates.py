"""CE.3.1: PredicateRegistry tests (P1/P2)."""

import pytest

from igl_cognitive.predicates import (
    PredicateRegistry,
    split_condition,
    PREDICATE_PREFIX,
    FLAG_PREFIX,
    MEMORY_PREFIX,
)


def is_math_request(context: dict) -> bool:
    return "mathematically" in context.get("text", "").lower()


def always_true(context: dict) -> bool:
    return True


# --- P1: registered predicate is retrieved and hashed ---

def test_p1_registered_predicate_retrieved():
    reg = PredicateRegistry({"text.is_math_request": ("1", is_math_request)})
    assert reg.has("text.is_math_request")
    version, fn = reg.get("text.is_math_request")
    assert version == "1"
    assert fn({"text": "prove mathematically"}) is True
    assert fn({"text": "tell a story"}) is False


def test_p1_registry_hash_is_deterministic():
    reg_a = PredicateRegistry({
        "a": ("1", always_true),
        "b": ("2", always_true),
    })
    reg_b = PredicateRegistry({
        "b": ("2", always_true),
        "a": ("1", always_true),
    })
    assert reg_a.hash() == reg_b.hash()


def test_p1_registry_hash_changes_with_version():
    reg_a = PredicateRegistry({"a": ("1", always_true)})
    reg_b = PredicateRegistry({"a": ("2", always_true)})
    assert reg_a.hash() != reg_b.hash()


# --- P2: unknown predicate is rejected ---

def test_p2_unknown_predicate_raises():
    reg = PredicateRegistry({"known": ("1", always_true)})
    assert reg.has("known")
    assert not reg.has("unknown")
    with pytest.raises(KeyError):
        reg.get("unknown")


def test_p2_registry_copies_input():
    source = {"a": ("1", always_true)}
    reg = PredicateRegistry(source)
    source["b"] = ("1", always_true)  # mutate original
    assert not reg.has("b")           # registry unaffected
    assert reg.names() == ("a",)


# --- split_condition ---

def test_split_condition_predicate():
    assert split_condition("predicate:foo") == ("predicate", "foo")


def test_split_condition_flag():
    assert split_condition("flag:foo") == ("flag", "foo")


def test_split_condition_memory():
    assert split_condition("memory:foo") == ("memory", "foo")


def test_split_condition_legacy():
    assert split_condition("foo") == ("legacy", "foo")


def test_split_condition_prefix_constants():
    assert PREDICATE_PREFIX == "predicate:"
    assert FLAG_PREFIX == "flag:"
    assert MEMORY_PREFIX == "memory:"


"""CE.3.2: Predicate evaluation in Engine (P3/P4/P5)."""

import pytest

from igl_cognitive.engine import Engine
from igl_cognitive.frame import CognitiveFrame
from igl_cognitive.predicates import PredicateRegistry
from igl_cognitive.rules import Rule
from igl_cognitive.trace import trace_hash


def failing(_ctx):
    raise RuntimeError("boom")


def is_math(ctx):
    return "mathematically" in ctx.get("text", "").lower()


def make_hard(rule_id: str, condition: str, **frame_overrides) -> Rule:
    frame = {"register": "verification", "coordinate_system": "mathematics", "strategy": "formal_verification"}
    frame.update(frame_overrides)
    return Rule(
        id=rule_id,
        priority="HARD",
        condition=condition,
        frame=frame,
        scope="t",
        weight=None,
        min_model_tier="strong",
    )


# --- P3: HARD predicate error -> UNDETERMINED, overrides other HARD success ---

def test_p3_hard_predicate_error_undetermined():
    reg = PredicateRegistry({"failing": ("1", failing)})
    good = Rule(
        id="GOOD_HARD",
        priority="HARD",
        condition="flag:good_on",
        frame={"register": "task", "coordinate_system": "engineering", "strategy": "practical_execution"},
        scope="t",
        weight=None,
        min_model_tier="medium",
    )
    bad = Rule(
        id="BAD_HARD",
        priority="HARD",
        condition="predicate:failing",
        frame={"register": "hypothesis", "coordinate_system": "philosophy", "strategy": "conceptual_exploration"},
        scope="t",
        weight=None,
    )
    engine = Engine(rules=[good, bad], predicate_registry=reg)
    trace = engine.select(context={"good_on": True})

    assert trace.event == "frame_undetermined"
    assert trace.undetermined_reason == "hard_predicate_error"
    assert trace.selected_frame is None
    # Both HARD evaluated, one error recorded
    errs = [e for e in trace.predicates_evaluated if e.get("error")]
    assert any(e["name"] == "failing" and e["error"] == "PREDICATE_EVALUATION_FAILED" for e in errs)


# --- P4: SOFT predicate error -> skipped, selection continues ---

def test_p4_soft_predicate_error_skipped():
    reg = PredicateRegistry({"failing": ("1", failing)})
    hard = Rule(
        id="HARD_REG",
        priority="HARD",
        condition="flag:on",
        frame={"register": "hypothesis"},
        scope="t",
        weight=None,
    )
    soft = Rule(
        id="SOFT_BAD",
        priority="SOFT",
        condition="predicate:failing",
        frame={"coordinate_system": "mathematics"},
        scope="t",
        weight=1,
        min_model_tier=None,
    )
    engine = Engine(rules=[hard, soft], predicate_registry=reg)
    trace = engine.select(context={"on": True})

    # No DEFAULT, no classifier, SOFT tie -> UNDETERMINED, but SOFT was attempted
    assert trace.event == "frame_undetermined"
    assert any(e["name"] == "failing" and e["error"] for e in trace.predicates_evaluated)


# --- P5: deterministic replay ---

def test_p5_deterministic_replay():
    reg = PredicateRegistry({"is_math": ("1", is_math)})
    rule = Rule(
        id="MATH",
        priority="HARD",
        condition="predicate:is_math",
        frame={"register": "verification", "coordinate_system": "mathematics", "strategy": "formal_verification"},
        scope="t",
        weight=None,
        min_model_tier="strong",
    )
    engine = Engine(rules=[rule], predicate_registry=reg)
    ctx = {"text": "prove mathematically"}

    t1 = engine.select(context=ctx)
    t2 = engine.select(context=ctx)

    assert t1.selected_frame == t2.selected_frame
    assert t1.predicate_registry_hash == t2.predicate_registry_hash
    assert t1.predicates_evaluated == t2.predicates_evaluated
    assert trace_hash(t1) == trace_hash(t2)


# --- Bonus: unknown predicate in rule -> ValueError at construction ---

def test_unknown_predicate_in_rule_rejected():
    rule = Rule(
        id="BAD",
        priority="HARD",
        condition="predicate:missing",
        frame={"register": "verification"},
        scope="t",
        weight=None,
    )
    with pytest.raises(ValueError):
        Engine(rules=[rule], predicate_registry=PredicateRegistry({}))
