"""Tests for Rule (CE.1-r3)."""

import pytest

from igl_cognitive.rules import (
    Rule,
    VALID_PRIORITIES,
    is_valid_rule,
    rule_to_dict,
    rule_from_dict,
    rule_hash,
    ruleset_hash,
)


def make_hard(**overrides) -> Rule:
    base = dict(
        id="EXPLICIT_MATH_VERIFICATION",
        priority="HARD",
        condition="explicit_math_proof_request",
        frame={"register": "verification", "coordinate_system": "mathematics"},
        scope="math_request",
        weight=None,
        min_model_tier="strong",
    )
    base.update(overrides)
    return Rule(**base)


def make_soft(**overrides) -> Rule:
    base = dict(
        id="KEEP_CURRENT_REGISTER",
        priority="SOFT",
        condition="user_continues_topic",
        frame={"register": "hypothesis"},
        scope="continuation",
        weight=1,
        min_model_tier=None,
    )
    base.update(overrides)
    return Rule(**base)


# --- basic validity ---

def test_valid_hard_rule():
    assert is_valid_rule(make_hard()) is True


def test_valid_soft_rule():
    assert is_valid_rule(make_soft()) is True


def test_invalid_priority():
    assert is_valid_rule(make_hard(priority="MAYBE")) is False


def test_empty_id_rejected():
    assert is_valid_rule(make_hard(id="")) is False


def test_empty_condition_rejected():
    assert is_valid_rule(make_hard(condition="")) is False


# --- HARD specifics ---

def test_hard_with_weight_rejected():
    assert is_valid_rule(make_hard(weight=2)) is False


def test_hard_with_valid_min_tier_accepted():
    assert is_valid_rule(make_hard(min_model_tier="medium")) is True


def test_hard_with_invalid_min_tier_rejected():
    assert is_valid_rule(make_hard(min_model_tier="huge")) is False


# --- SOFT specifics ---

def test_soft_with_min_tier_rejected():
    assert is_valid_rule(make_soft(min_model_tier="strong")) is False


def test_soft_without_weight_rejected():
    assert is_valid_rule(make_soft(weight=None)) is False


def test_soft_with_zero_weight_rejected():
    assert is_valid_rule(make_soft(weight=0)) is False


def test_soft_with_negative_weight_rejected():
    assert is_valid_rule(make_soft(weight=-1)) is False


def test_soft_with_float_weight_rejected():
    # T18: веса — positive int, не float
    assert is_valid_rule(make_soft(weight=1.5)) is False


def test_soft_with_bool_weight_rejected():
    # bool — подкласс int, но не валидный вес
    assert is_valid_rule(make_soft(weight=True)) is False


# --- frame fields ---

def test_unknown_frame_field_rejected():
    r = make_hard(frame={"unknown_field": "x"})
    assert is_valid_rule(r) is False


def test_unknown_field_in_frame_rejected():
    r = make_hard(frame={"register": "verification", "weird": "x"})
    assert is_valid_rule(r) is False


# --- serialization ---

def test_rule_dict_roundtrip_hard():
    r = make_hard()
    back = rule_from_dict(rule_to_dict(r))
    assert back == r


def test_rule_dict_roundtrip_soft():
    r = make_soft()
    back = rule_from_dict(rule_to_dict(r))
    assert back == r


# --- hashes ---

def test_rule_hash_is_canonical():
    assert rule_hash(make_hard()) == rule_hash(make_hard())


def test_ruleset_hash_order_independent():
    # T15: порядок правил не влияет на хеш
    a = make_hard()
    b = make_soft()
    assert ruleset_hash([a, b]) == ruleset_hash([b, a])


def test_ruleset_hash_detects_change():
    a = make_hard()
    b = make_hard(id="OTHER_RULE")
    assert ruleset_hash([a]) != ruleset_hash([b])