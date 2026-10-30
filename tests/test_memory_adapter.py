"""Tests for Memory Gate Adapter (CE.2.1, mock Gate)."""

from igl_cognitive.memory_adapter import (
    AllowedMemory,
    MemoryAdapterDiagnostics,
    build_allowed_memory,
)


def belief(key: str, value) -> dict:
    return {"content": {"key": key, "value": value}}


def test_empty_gate_result():
    allowed, diag = build_allowed_memory({"accepted": [], "withheld": [], "constraints": []})
    assert allowed.memory_context == {}
    assert allowed.allowed_memory_ref is not None
    assert diag.withheld_count == 0
    assert diag.constraints_count == 0


def test_accepted_beliefs_become_context():
    gate = {
        "accepted": [
            belief("preferred_reasoning", "mathematics"),
            belief("response_style", "concise"),
        ],
        "withheld": [],
        "constraints": [],
    }
    allowed, diag = build_allowed_memory(gate)
    assert allowed.memory_context["preferred_reasoning"] == "mathematics"
    assert allowed.memory_context["response_style"] == "concise"
    assert diag.withheld_count == 0


def test_withheld_not_in_context():
    gate = {
        "accepted": [belief("preferred_reasoning", "mathematics")],
        "withheld": [
            {"id": "b1", "reason": "user_semantic_block"},
            {"id": "b2", "reason": "not_trusted:SUPERSEDED"},
        ],
        "constraints": [],
    }
    allowed, diag = build_allowed_memory(gate)
    assert "preferred_reasoning" in allowed.memory_context
    assert diag.withheld_count == 2
    assert "user_semantic_block" in diag.withheld_reasons
    assert "not_trusted:SUPERSEDED" in diag.withheld_reasons


def test_constraints_preserved_but_not_in_context():
    gate = {
        "accepted": [],
        "withheld": [],
        "constraints": [{"type": "avoid_headwear", "scope": "character"}],
    }
    allowed, diag = build_allowed_memory(gate)
    assert allowed.memory_context == {}
    assert diag.constraints_count == 1
    assert diag.constraints[0]["type"] == "avoid_headwear"


def test_allowed_memory_ref_independent_of_order():
    gate_a = {
        "accepted": [belief("a", 1), belief("b", 2)],
        "withheld": [], "constraints": [],
    }
    gate_b = {
        "accepted": [belief("b", 2), belief("a", 1)],
        "withheld": [], "constraints": [],
    }
    a1, _ = build_allowed_memory(gate_a)
    a2, _ = build_allowed_memory(gate_b)
    assert a1.allowed_memory_ref == a2.allowed_memory_ref
    assert a1.memory_context == a2.memory_context


def test_allowed_memory_ref_changes_with_content():
    gate_a = {
        "accepted": [belief("a", 1)],
        "withheld": [], "constraints": [],
    }
    gate_b = {
        "accepted": [belief("a", 2)],
        "withheld": [], "constraints": [],
    }
    a1, _ = build_allowed_memory(gate_a)
    a2, _ = build_allowed_memory(gate_b)
    assert a1.allowed_memory_ref != a2.allowed_memory_ref


def test_forget_removes_from_context():
    """Simulate: before forget preferred_reasoning present, after forget absent."""
    before = {
        "accepted": [belief("preferred_reasoning", "mathematics")],
        "withheld": [], "constraints": [],
    }
    after = {
        "accepted": [],  # after forget, Gate no longer returns it
        "withheld": [{"id": "b1", "reason": "forgotten"}],
        "constraints": [],
    }
    a_before, _ = build_allowed_memory(before)
    a_after, d_after = build_allowed_memory(after)
    assert "preferred_reasoning" in a_before.memory_context
    assert "preferred_reasoning" not in a_after.memory_context
    assert d_after.withheld_count == 1


def test_malformed_belief_skipped():
    gate = {
        "accepted": [
            {"content": "not a dict"},
            {"content": {"no_key": "x"}},
            belief("valid", 42),
        ],
        "withheld": [], "constraints": [],
    }
    allowed, _ = build_allowed_memory(gate)
    assert allowed.memory_context == {"valid": 42}