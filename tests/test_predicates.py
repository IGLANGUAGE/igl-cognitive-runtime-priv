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