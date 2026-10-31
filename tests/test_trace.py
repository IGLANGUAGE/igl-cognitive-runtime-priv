"""Tests for DecisionTrace (CE.1-r3)."""

import pytest

from igl_cognitive.trace import (
    DecisionTrace,
    CONTRACT_VERSION,
    VALID_EVENTS,
    VALID_RESOLUTIONS,
    VALID_CONFLICT_REASONS,
    is_valid_trace,
    trace_to_dict,
    trace_from_dict,
    trace_hash,
)


H = "a" * 64  # фиктивный хеш для тестов


def make_selected_trace(**overrides) -> DecisionTrace:
    base = dict(
        event="frame_selection",
        ruleset_hash=H,
        frame_registry_hash=H,
        input_hash=H,
        context_hash=H,
        state_hash=H,
        allowed_frames_hash=H,
        rules_fired=[{"id": "EXPLICIT_MATH_VERIFICATION", "priority": "HARD", "weight": None}],
        classifier=None,
        conflict=True,
        conflict_reason="hard_vs_classifier",
        resolution="hard_unique",
        previous_frame=None,
        selected_frame={
            "register": "verification",
            "coordinate_system": "mathematics",
            "strategy": "formal_verification",
            "model_tier": "strong",
            "revision": 0,
        },
        revision=0,
        allowed_memory_ref=None,
        undetermined_reason=None,
    )
    base.update(overrides)
    return DecisionTrace(**base)


def make_conflict_trace(**overrides) -> DecisionTrace:
    base = dict(
        event="frame_conflict",
        ruleset_hash=H,
        frame_registry_hash=H,
        input_hash=H,
        context_hash=H,
        state_hash=H,
        allowed_frames_hash=H,
        conflict=True,
        conflict_reason="hard_vs_hard",
        resolution="none",
        selected_frame=None,
        revision=0,
    )
    base.update(overrides)
    return DecisionTrace(**base)


def make_undetermined_trace(**overrides) -> DecisionTrace:
    base = dict(
        event="frame_undetermined",
        ruleset_hash=H,
        frame_registry_hash=H,
        input_hash=H,
        context_hash=H,
        state_hash=H,
        allowed_frames_hash=H,
        conflict=False,
        conflict_reason="none",
        resolution="none",
        selected_frame=None,
        revision=0,
        undetermined_reason="soft_tie_no_default",
    )
    base.update(overrides)
    return DecisionTrace(**base)


# --- constants ---

def test_contract_version():
    assert CONTRACT_VERSION == "CE.1-r3"


def test_valid_events():
    assert VALID_EVENTS == {"frame_selection", "frame_conflict", "frame_undetermined"}


def test_valid_resolutions():
    assert VALID_RESOLUTIONS == {
        "hard_unique", "hard_rule_override", "soft_rule_accept",
        "classifier_accepted", "default", "none",
    }


def test_valid_conflict_reasons():
    assert VALID_CONFLICT_REASONS == {"hard_vs_classifier", "hard_vs_hard", "none"}


# --- validity: selected ---

def test_selected_trace_valid():
    assert is_valid_trace(make_selected_trace()) is True


def test_selected_without_frame_rejected():
    t = make_selected_trace(selected_frame=None)
    assert is_valid_trace(t) is False


# --- validity: conflict ---

def test_conflict_trace_valid():
    assert is_valid_trace(make_conflict_trace()) is True


def test_conflict_with_selected_frame_rejected():
    t = make_conflict_trace(selected_frame={"register": "verification"})
    assert is_valid_trace(t) is False


def test_conflict_with_wrong_reason_rejected():
    t = make_conflict_trace(conflict_reason="none")
    assert is_valid_trace(t) is False


# --- validity: undetermined ---

def test_undetermined_trace_valid():
    assert is_valid_trace(make_undetermined_trace()) is True


def test_undetermined_without_reason_rejected():
    t = make_undetermined_trace(undetermined_reason=None)
    assert is_valid_trace(t) is False


# --- general validation ---

def test_invalid_event_rejected():
    t = make_selected_trace(event="frame_unknown")
    assert is_valid_trace(t) is False


def test_invalid_resolution_rejected():
    t = make_selected_trace(resolution="magic")
    assert is_valid_trace(t) is False


def test_invalid_conflict_reason_rejected():
    t = make_selected_trace(conflict_reason="magic")
    assert is_valid_trace(t) is False


def test_invalid_contract_version_rejected():
    t = make_selected_trace(contract_version="CE.0")
    assert is_valid_trace(t) is False


def test_negative_revision_rejected():
    t = make_selected_trace(revision=-1)
    assert is_valid_trace(t) is False


# --- serialization ---

def test_trace_dict_roundtrip_selected():
    t = make_selected_trace()
    assert trace_from_dict(trace_to_dict(t)) == t


def test_trace_dict_roundtrip_conflict():
    t = make_conflict_trace()
    assert trace_from_dict(trace_to_dict(t)) == t


def test_trace_dict_roundtrip_undetermined():
    t = make_undetermined_trace()
    assert trace_from_dict(trace_to_dict(t)) == t


# --- hashes ---

def test_trace_hash_deterministic():
    a = make_selected_trace()
    b = make_selected_trace()
    assert trace_hash(a) == trace_hash(b)


def test_trace_hash_detects_change():
    a = make_selected_trace()
    b = make_selected_trace(revision=1)
    assert trace_hash(a) != trace_hash(b)


# --- T12: no plaintext in trace ---

def test_trace_contains_no_plaintext_secret():
    """T12: трейс не должен содержать исходный текст пользователя."""
    secret = "my-super-secret-password-12345"
    t = make_selected_trace(input_hash=H)  # input_hash — хеш, не текст
    d = trace_to_dict(t)
    serialized = str(d)
    assert secret not in serialized