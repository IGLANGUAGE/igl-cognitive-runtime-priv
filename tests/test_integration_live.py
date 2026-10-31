"""CE.2.2 live integration: IGL Memory -> Adapter -> Cognitive Engine.

Requires:
  - running IGL Memory server at IGL_BASE_URL (default http://127.0.0.1:8000)
  - IGL_USER_TOKEN in environment

Skips if SDK missing or IGL_USER_TOKEN missing.
Fails (does not skip) if token is set but server is unreachable.
"""

from __future__ import annotations

import os

import pytest

igl_client = pytest.importorskip("igl_client")

from igl_client import IglClient

from igl_cognitive.engine import Engine
from igl_cognitive.memory_adapter import build_allowed_memory
from igl_cognitive.rules import Rule


pytestmark = pytest.mark.live


BASE_URL = os.environ.get("IGL_BASE_URL", "http://127.0.0.1:8000")
USER_TOKEN = os.environ.get("IGL_USER_TOKEN", "")

# Single test user for the whole live suite.
# Isolation between scenarios is done via forget.
TEST_USER_ID = "ce22-live-001"

# Map Gate belief -> Engine memory_context boolean.
# Explicit table only. No guessing.
REASONING_MAP = {
    ("preferred_reasoning", "mathematics"): "preferred_reasoning_math",
    ("preferred_reasoning", "philosophy"): "preferred_reasoning_philosophy",
}


def _client() -> IglClient:
    if not USER_TOKEN:
        pytest.skip("IGL_USER_TOKEN not set")
    return IglClient(base_url=BASE_URL, token=USER_TOKEN)


def _engine() -> Engine:
    return Engine(rules=[
        Rule(
            id="MEMORY_MATH",
            priority="HARD",
            condition="memory.preferred_reasoning_math",
            frame={
                "register": "hypothesis",
                "coordinate_system": "mathematics",
                "strategy": "formal_derivation",
            },
            scope="memory",
            weight=None,
            min_model_tier="strong",
        ),
        Rule(
            id="MEMORY_PHILOSOPHY",
            priority="HARD",
            condition="memory.preferred_reasoning_philosophy",
            frame={
                "register": "hypothesis",
                "coordinate_system": "philosophy",
                "strategy": "conceptual_exploration",
            },
            scope="memory",
            weight=None,
            min_model_tier="strong",
        ),
    ])


def _to_memory_context(accepted: list[dict]) -> dict:
    """Map accepted beliefs to Engine memory_context.

    Supports both mock shape (content.key/value) and real Gate shape
    (belief.value.key/value). Only explicit REASONING_MAP entries become
    boolean flags.
    """
    ctx: dict = {}
    for item in accepted:
        if not isinstance(item, dict):
            continue
        # Real Gate shape
        inner = item.get("belief")
        if isinstance(inner, dict):
            value_obj = inner.get("value")
            if isinstance(value_obj, dict):
                key = value_obj.get("key")
                value = value_obj.get("value")
                flag = REASONING_MAP.get((key, value))
                if flag:
                    ctx[flag] = True
            continue
        # Mock shape
        content = item.get("content")
        if isinstance(content, dict):
            key = content.get("key")
            value = content.get("value")
            flag = REASONING_MAP.get((key, value))
            if flag:
                ctx[flag] = True
    return ctx


def _gate_dict(result) -> dict:
    """Convert GateResult pydantic model to plain dict for adapter."""
    # SDK GateResult has .accepted, .withheld, .constraints lists of models
    def _to_plain(item):
        if hasattr(item, "model_dump"):
            return item.model_dump()
        if isinstance(item, dict):
            return item
        return {}

    return {
        "accepted": [_to_plain(x) for x in getattr(result, "accepted", [])],
        "withheld": [_to_plain(x) for x in getattr(result, "withheld", [])],
        "constraints": [_to_plain(x) for x in getattr(result, "constraints", [])],
    }


def _forget_all(client: IglClient) -> None:
    """Forget the known test semantic key between scenarios.

    Uses the full IGL semantic key shape:
      interaction_preference:<key>:<applicability_json>

    For our tests applicability is {}, so the key is:
      interaction_preference:preferred_reasoning:{}
    """
    try:
        client.forget_semantic(
            semantic_key="interaction_preference:preferred_reasoning:{}",
            reason={"why": "ce22 test isolation"},
        )
    except Exception:
        # Nothing to forget is fine.
        pass


# --- L1: Record -> Compile -> Gate -> Engine ---

def test_l1_record_compile_gate_engine():
    """L1: allowed memory preference influences CognitiveFrame.

    Steps:
      1. record preferred_reasoning=mathematics
      2. compile
      3. gate
      4. adapter -> memory_context
      5. Engine.select -> hard_unique hypothesis/mathematics/formal_derivation/strong
    """
    client = _client()
    _forget_all(client)

    event = client.record(
        event_type="explicit_preference",
        content={"key": "preferred_reasoning", "value": "mathematics"},
    )
    assert event.id

    compile_result = client.compile([event.id])
    assert compile_result.committed, "compile produced no beliefs"

    gate_result = client.gate(purpose="reasoning_selection", context={})
    gate_dict = _gate_dict(gate_result)
    assert gate_dict["accepted"], "gate accepted is empty"

    allowed, diagnostics = build_allowed_memory(gate_dict)
    assert diagnostics.withheld_count >= 0

    # Adapter returns raw key: value pairs. Mapping to Engine boolean flags
    # is a Cognitive Runtime concern, not an adapter concern.
    memory_context = _to_memory_context(gate_dict["accepted"])
    assert memory_context == {"preferred_reasoning_math": True}, (
        f"unexpected memory_context: {memory_context}"
    )

    engine = _engine()
    trace = engine.select(
        context={},
        classifier_proposal=None,
        previous_frame=None,
        memory_context=memory_context,
        allowed_memory_ref=allowed.allowed_memory_ref,
    )

    assert trace.event == "frame_selection"
    assert trace.resolution == "hard_unique"
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "hypothesis"
    assert trace.selected_frame["coordinate_system"] == "mathematics"
    assert trace.selected_frame["strategy"] == "formal_derivation"
    assert trace.selected_frame["model_tier"] == "strong"
    assert trace.allowed_memory_ref == allowed.allowed_memory_ref


# --- L2: Correction ---

def test_l2_correction():
    """L2: correction changes which belief Gate serves.

    Steps:
      1. record preferred_reasoning=mathematics
      2. compile
      3. correct(belief_id, value=philosophy)
      4. gate -> accepted contains philosophy, NOT mathematics
      5. memory_context == {preferred_reasoning_philosophy: True}
      6. Engine -> hypothesis/philosophy/conceptual_exploration/strong
    """
    client = _client()
    _forget_all(client)

    event = client.record(
        event_type="explicit_preference",
        content={"key": "preferred_reasoning", "value": "mathematics"},
    )
    assert event.id

    compile_result = client.compile([event.id])
    assert compile_result.committed, "compile produced no beliefs"
    belief_id = compile_result.committed[0].id

    correct_result = client.correct(
        belief_id=belief_id,
        value={"key": "preferred_reasoning", "value": "philosophy"},
    )
    assert correct_result is not None

    gate_result = client.gate(purpose="reasoning_selection", context={})
    gate_dict = _gate_dict(gate_result)
    assert gate_dict["accepted"], "gate accepted is empty after correction"

    # Accepted must contain philosophy, NOT mathematics
    accepted_values = []
    for item in gate_dict["accepted"]:
        inner = item.get("belief", {})
        value_obj = inner.get("value", {})
        if value_obj.get("key") == "preferred_reasoning":
            accepted_values.append(value_obj.get("value"))

    assert "philosophy" in accepted_values, (
        f"corrected value not in accepted: {accepted_values}"
    )
    assert "mathematics" not in accepted_values, (
        f"old value still in accepted after correction: {accepted_values}"
    )

    # Build memory_context via explicit mapping
    memory_context = _to_memory_context(gate_dict["accepted"])
    assert memory_context == {"preferred_reasoning_philosophy": True}, (
        f"unexpected memory_context: {memory_context}"
    )

    allowed, _ = build_allowed_memory(gate_dict)

    engine = _engine()
    trace = engine.select(
        context={},
        classifier_proposal=None,
        previous_frame=None,
        memory_context=memory_context,
        allowed_memory_ref=allowed.allowed_memory_ref,
    )

    assert trace.event == "frame_selection"
    assert trace.resolution == "hard_unique"
    assert trace.selected_frame is not None
    assert trace.selected_frame["register"] == "hypothesis"
    assert trace.selected_frame["coordinate_system"] == "philosophy"
    assert trace.selected_frame["strategy"] == "conceptual_exploration"
    assert trace.selected_frame["model_tier"] == "strong"


# --- L3: Reject ---

def test_l3_reject():
    """L3: rejected belief does not appear in Gate accepted.

    Steps:
      1. record preferred_reasoning=mathematics
      2. compile
      3. reject(belief_id)
      4. gate -> accepted does NOT contain this belief
      5. memory_context == {}
      6. Engine -> UNDETERMINED
    """
    client = _client()
    _forget_all(client)

    event = client.record(
        event_type="explicit_preference",
        content={"key": "preferred_reasoning", "value": "mathematics"},
    )
    assert event.id

    compile_result = client.compile([event.id])
    assert compile_result.committed, "compile produced no beliefs"
    belief_id = compile_result.committed[0].id

    reject_result = client.reject(
        belief_id=belief_id,
        reason={"why": "ce22-live L3: reject test"},
    )
    assert reject_result is not None

    gate_result = client.gate(purpose="reasoning_selection", context={})
    gate_dict = _gate_dict(gate_result)

    # Accepted must NOT contain the rejected belief
    accepted_values = []
    for item in gate_dict["accepted"]:
        inner = item.get("belief", {})
        value_obj = inner.get("value", {})
        if value_obj.get("key") == "preferred_reasoning":
            accepted_values.append(value_obj.get("value"))

    assert "mathematics" not in accepted_values, (
        f"rejected value still in accepted: {accepted_values}"
    )

    memory_context = _to_memory_context(gate_dict["accepted"])
    assert memory_context == {}, (
        f"unexpected memory_context after reject: {memory_context}"
    )

    allowed, diagnostics = build_allowed_memory(gate_dict)
    assert diagnostics.withheld_count >= 0

    engine = _engine()
    trace = engine.select(
        context={},
        classifier_proposal=None,
        previous_frame=None,
        memory_context=memory_context,
        allowed_memory_ref=allowed.allowed_memory_ref,
    )

    assert trace.event == "frame_undetermined"
    assert trace.selected_frame is None
    fired_ids = [r["id"] for r in trace.rules_fired]
    assert "MEMORY_MATH" not in fired_ids
    assert "MEMORY_PHILOSOPHY" not in fired_ids


# --- L4: Forget ---

def test_l4_forget():
    """L4: forgotten belief is not served by Gate after forget_semantic.

    Steps:
      1. record preferred_reasoning=mathematics
      2. compile
      3. gate -> accepted contains mathematics (before forget)
      4. forget_semantic("interaction_preference:preferred_reasoning:{}")
      5. gate -> accepted does NOT contain it (after forget)
      6. memory_context == {}
      7. Engine -> UNDETERMINED
    """
    client = _client()
    _forget_all(client)

    event = client.record(
        event_type="explicit_preference",
        content={"key": "preferred_reasoning", "value": "mathematics"},
    )
    assert event.id

    compile_result = client.compile([event.id])
    assert compile_result.committed, "compile produced no beliefs"

    # Before forget: accepted contains mathematics
    gate_before = _gate_dict(client.gate(purpose="reasoning_selection", context={}))
    values_before = [
        item.get("belief", {}).get("value", {}).get("value")
        for item in gate_before["accepted"]
        if item.get("belief", {}).get("value", {}).get("key") == "preferred_reasoning"
    ]
    assert "mathematics" in values_before, (
        f"precondition failed: mathematics not in accepted before forget: {values_before}"
    )

    # Forget
    forget_result = client.forget_semantic(
        semantic_key="interaction_preference:preferred_reasoning:{}",
        reason={"why": "ce22-live L4: forget test"},
    )
    assert forget_result is not None

    # After forget: accepted does NOT contain mathematics
    gate_after = _gate_dict(client.gate(purpose="reasoning_selection", context={}))
    values_after = [
        item.get("belief", {}).get("value", {}).get("value")
        for item in gate_after["accepted"]
        if item.get("belief", {}).get("value", {}).get("key") == "preferred_reasoning"
    ]
    assert "mathematics" not in values_after, (
        f"forgotten value still in accepted: {values_after}"
    )

    memory_context = _to_memory_context(gate_after["accepted"])
    assert memory_context == {}, (
        f"unexpected memory_context after forget: {memory_context}"
    )

    allowed, _ = build_allowed_memory(gate_after)
    engine = _engine()
    trace = engine.select(
        context={},
        classifier_proposal=None,
        previous_frame=None,
        memory_context=memory_context,
        allowed_memory_ref=allowed.allowed_memory_ref,
    )

    assert trace.event == "frame_undetermined"
    assert trace.selected_frame is None
