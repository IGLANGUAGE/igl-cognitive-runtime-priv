"""CE.3.3 / P6: natural-language frame selection via deterministic predicates."""

from igl_cognitive.builtin_predicates import (
    BUILTIN_PREDICATES,
    contains_math_request,
)
from igl_cognitive.engine import Engine
from igl_cognitive.predicates import PredicateRegistry
from igl_cognitive.rules import Rule


def math_rule() -> Rule:
    return Rule(
        id="EXPLICIT_MATH",
        priority="HARD",
        condition="predicate:text.contains_math_request",
        frame={
            "register": "verification",
            "coordinate_system": "mathematics",
            "strategy": "formal_verification",
        },
        scope="nl_text",
        weight=None,
        min_model_tier="strong",
    )


def make_engine() -> Engine:
    reg = PredicateRegistry({"text.contains_math_request": ("1", contains_math_request)})
    return Engine(rules=[math_rule()], predicate_registry=reg)


# --- P6a: Russian imperative math request ---

def test_p6a_russian_math_request():
    engine = make_engine()
    trace = engine.select(context={"text": "Докажи математически"})

    assert trace.event == "frame_selection"
    assert trace.resolution == "hard_unique"
    assert trace.selected_frame["register"] == "verification"
    assert trace.selected_frame["coordinate_system"] == "mathematics"
    assert trace.selected_frame["strategy"] == "formal_verification"
    assert trace.selected_frame["model_tier"] == "strong"
    assert any(
        e["name"] == "text.contains_math_request" and e["result"] is True
        for e in trace.predicates_evaluated
    )


# --- P6b: English imperative math request ---

def test_p6b_english_math_request():
    engine = make_engine()
    trace = engine.select(context={"text": "Please prove mathematically that 2+2=4"})
    assert trace.event == "frame_selection"
    assert trace.selected_frame["coordinate_system"] == "mathematics"
    assert any(
        e["name"] == "text.contains_math_request" and e["result"] is True
        for e in trace.predicates_evaluated
    )


# --- P6c: no math request ---

def test_p6c_no_math_request():
    engine = make_engine()
    trace = engine.select(context={"text": "Расскажи сказку"})
    assert trace.event == "frame_undetermined"
    assert trace.selected_frame is None
    assert any(
        e["name"] == "text.contains_math_request"
        and e["result"] is False
        and e["error"] is None
        for e in trace.predicates_evaluated
    )


# --- P6d: empty text ---

def test_p6d_empty_text():
    engine = make_engine()
    trace = engine.select(context={})
    assert trace.event == "frame_undetermined"


# --- P6e: mention of mathematical proof without request ---

def test_p6e_mention_without_request():
    """Mentioning a proof is not requesting one."""
    assert contains_math_request({
        "text": "Вчера мы обсуждали математическое доказательство."
    }) is False
    assert contains_math_request({
        "text": "The paper discusses a formal proof of the theorem."
    }) is False

    engine = make_engine()
    trace = engine.select(context={
        "text": "Вчера мы обсуждали математическое доказательство."
    })
    assert trace.event == "frame_undetermined"
    assert any(
        e["name"] == "text.contains_math_request"
        and e["result"] is False
        for e in trace.predicates_evaluated
    )


# --- BUILTIN_PREDICATES registry is consistent ---

def test_builtin_registry_contains_predicate():
    assert "text.contains_math_request" in BUILTIN_PREDICATES
    version, fn = BUILTIN_PREDICATES["text.contains_math_request"]
    assert version == "1"
    assert fn({"text": "Докажи математически"}) is True
    assert fn({"text": "Расскажи сказку"}) is False