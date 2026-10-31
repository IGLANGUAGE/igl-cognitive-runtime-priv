"""CE.2.3-live: Two Johns on real IGL Memory.

Requires:
  - running IGL server
  - IGL_USER_TOKEN_A (John A)
  - IGL_USER_TOKEN_B (John B)

JL1: different memory -> different frames
JL2: same memory -> same frames
JL3: forget for A -> no dependency on forgotten
JL4: deterministic replay per John
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
TOKEN_A = os.environ.get("IGL_USER_TOKEN_A", "")
TOKEN_B = os.environ.get("IGL_USER_TOKEN_B", "")


REASONING_MAP = {
    ("preferred_reasoning", "mathematics"): "preferred_reasoning_math",
    ("preferred_reasoning", "philosophy"): "preferred_reasoning_philosophy",
}

SEMANTIC_KEY = "interaction_preference:preferred_reasoning:{}"


def _client(token: str) -> IglClient:
    if not token:
        pytest.skip("IGL_USER_TOKEN_A / IGL_USER_TOKEN_B not set")
    return IglClient(base_url=BASE_URL, token=token)


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


def _gate_dict(result) -> dict:
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


def _to_memory_context(accepted: list[dict]) -> dict:
    ctx: dict = {}
    for item in accepted:
        if not isinstance(item, dict):
            continue
        inner = item.get("belief")
        if isinstance(inner, dict):
            value_obj = inner.get("value")
            if isinstance(value_obj, dict):
                flag = REASONING_MAP.get((value_obj.get("key"), value_obj.get("value")))
                if flag:
                    ctx[flag] = True
            continue
        content = item.get("content")
        if isinstance(content, dict):
            flag = REASONING_MAP.get((content.get("key"), content.get("value")))
            if flag:
                ctx[flag] = True
    return ctx


def _forget_all(client: IglClient) -> None:
    try:
        client.forget_semantic(semantic_key=SEMANTIC_KEY, reason={"why": "ce23 test isolation"})
    except Exception:
        pass


def _seed_preference(client: IglClient, value: str) -> None:
    event = client.record(
        event_type="explicit_preference",
        content={"key": "preferred_reasoning", "value": value},
    )
    assert event.id
    compile_result = client.compile([event.id])
    assert compile_result.committed, f"compile produced no beliefs for {value}"


def _select_frame(client: IglClient):
    gate_result = client.gate(purpose="reasoning_selection", context={})
    gate_dict = _gate_dict(gate_result)
    allowed, _ = build_allowed_memory(gate_dict)
    memory_context = _to_memory_context(gate_dict["accepted"])
    engine = _engine()
    trace = engine.select(
        context={},
        classifier_proposal=None,
        previous_frame=None,
        memory_context=memory_context,
        allowed_memory_ref=allowed.allowed_memory_ref,
    )
    return trace, memory_context, allowed


# --- JL1: different memory -> different frames ---

def test_jl1_different_experience_different_frames():
    a = _client(TOKEN_A)
    b = _client(TOKEN_B)
    _forget_all(a)
    _forget_all(b)

    _seed_preference(a, "mathematics")
    _seed_preference(b, "philosophy")

    trace_a, ctx_a, ref_a = _select_frame(a)
    trace_b, ctx_b, ref_b = _select_frame(b)

    assert ctx_a == {"preferred_reasoning_math": True}
    assert ctx_b == {"preferred_reasoning_philosophy": True}

    assert trace_a.event == "frame_selection"
    assert trace_a.resolution == "hard_unique"
    assert trace_a.selected_frame["coordinate_system"] == "mathematics"

    assert trace_b.event == "frame_selection"
    assert trace_b.resolution == "hard_unique"
    assert trace_b.selected_frame["coordinate_system"] == "philosophy"

    assert trace_a.selected_frame != trace_b.selected_frame
    assert ref_a != ref_b

    fired_a = [r["id"] for r in trace_a.rules_fired]
    fired_b = [r["id"] for r in trace_b.rules_fired]
    assert "MEMORY_MATH" in fired_a
    assert "MEMORY_PHILOSOPHY" in fired_b


# --- JL2: same memory -> same frame ---

def test_jl2_same_experience_same_frame():
    a = _client(TOKEN_A)
    b = _client(TOKEN_B)
    _forget_all(a)
    _forget_all(b)

    _seed_preference(a, "mathematics")
    _seed_preference(b, "mathematics")

    trace_a, ctx_a, _ = _select_frame(a)
    trace_b, ctx_b, _ = _select_frame(b)

    assert ctx_a == ctx_b == {"preferred_reasoning_math": True}
    assert trace_a.selected_frame == trace_b.selected_frame
    assert trace_a.resolution == trace_b.resolution


# --- JL3: forget A -> no dependency ---

def test_jl3_experience_removal():
    a = _client(TOKEN_A)
    _forget_all(a)

    _seed_preference(a, "mathematics")

    before, ctx_before, ref_before = _select_frame(a)
    assert ctx_before == {"preferred_reasoning_math": True}
    assert before.event == "frame_selection"

    _forget_all(a)

    after, ctx_after, ref_after = _select_frame(a)
    assert ctx_after == {}
    assert after.event == "frame_undetermined"
    assert after.selected_frame is None
    fired_ids = [r["id"] for r in after.rules_fired]
    assert "MEMORY_MATH" not in fired_ids
    assert ref_after != ref_before


# --- JL4: deterministic replay per John ---

def test_jl4_deterministic_replay():
    from igl_cognitive.trace import trace_hash

    a = _client(TOKEN_A)
    _forget_all(a)
    _seed_preference(a, "mathematics")

    t1, _, _ = _select_frame(a)
    t2, _, _ = _select_frame(a)

    assert t1.selected_frame == t2.selected_frame
    assert t1.revision == t2.revision
    assert trace_hash(t1) == trace_hash(t2)