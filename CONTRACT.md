# IGL Cognitive Runtime — Contract CE.1-r3

Status: CLOSED (engine, adapter, live IGL integration)

This document describes the contract that the implementation satisfies.
It is aligned with the actual code, not an aspirational design.

---

## 1. CognitiveFrame

A single consistent configuration.

Fields:
- `register`: one of `conversation`, `hypothesis`, `verification`, `task`, `memory`
- `coordinate_system`: one of `none`, `mathematics`, `philosophy`, `empirics`, `engineering`
- `strategy`: one of `conceptual_exploration`, `formal_verification`, `formal_derivation`, `practical_execution`, `recall`
- `model_tier`: one of `small`, `medium`, `strong`
- `revision`: integer >= 0

A frame is **valid** iff its triple `(register, coordinate_system, strategy)` is in
`VALID_FRAMES` and `model_tier` is in `VALID_TIERS`.

`VALID_FRAMES` (7 triples):
("conversation", "none", "conceptual_exploration")
("hypothesis", "philosophy", "conceptual_exploration")
("hypothesis", "mathematics", "formal_derivation")
("verification", "mathematics", "formal_verification")
("verification", "empirics", "formal_verification")
("task", "engineering", "practical_execution")
("memory", "none", "recall")


`VALID_TIERS = {"small", "medium", "strong"}`.

`revision` is part of the frame but **excluded** from configuration comparison.

---

## 2. Rule

Fields:
- `id`: unique string
- `priority`: `HARD` or `SOFT`
- `condition`: key in the effective context
  - plain key: `"explicit_math_verification"` -> `context["explicit_math_verification"]`
  - memory key: `"memory.preferred_reasoning_math"` -> `context["memory"]["preferred_reasoning_math"]`
- `frame`: partial frame (subset of `register`, `coordinate_system`, `strategy`)
- `scope`: string (documentation only at this stage)
- `weight`: positive integer, **SOFT only**
- `min_model_tier`: `small` | `medium` | `strong`, **HARD only**

Constraints:
- HARD: `frame` fields are exact; `min_model_tier` is a lower bound (not an exact value);
  `weight` must be `None`.
- SOFT: `frame` is a partial match; `weight` is a positive integer
  (float and bool rejected); `min_model_tier` must be `None`.

Natural-language predicates are **not connected yet** (CE.3).
At this stage `condition` is a boolean flag in the context.

---

## 3. Selection

Given applicable HARD rules:

1. Compute `ALLOWED`: all valid frames that satisfy all HARD rules.
   - exact match on `register`, `coordinate_system`, `strategy`;
   - `model_tier >= combined_min_model_tier`,
     where `combined_min_model_tier` is the maximum of applicable `min_model_tier` values.
2. If `ALLOWED` is empty -> `FRAME_CONFLICT`.
3. If `ALLOWED` has exactly one frame -> `hard_unique`.
4. If `ALLOWED` has more than one frame:
   a. If the classifier proposal is valid and inside `ALLOWED` -> `classifier_accepted`.
   b. Otherwise rank `ALLOWED` by applicable SOFT rules:
      `score(frame) = sum(weight of SOFT rules fully satisfied by frame)`.
   c. Unique maximum -> `soft_rule_accept`.
   d. Tie:
      - if `DEFAULT_SAFE_FRAME` is set and inside `ALLOWED` -> `default`;
      - otherwise -> `UNDETERMINED`.

`UNDETERMINED` reasons:
- `no_applicable_rule_no_valid_proposal_no_default` - no HARD, no SOFT, no classifier, no default;
- `soft_tie_no_default` - SOFT tie, no default.

Order of rules in a list does not affect the result.
`ruleset_hash` is normalized (sorted by id and priority).

---

## 4. Revision

- `revision` increases only when the selected configuration (without `revision`)
  differs from `previous_frame` (without `revision`).
- Same configuration -> same `revision`, even on repeated calls.
- `FRAME_CONFLICT` and `UNDETERMINED` do not increase revision.
- Configuration comparison **excludes** `revision`.
- `state_hash` **includes** `revision`.

---

## 5. DecisionTrace

Fields:
- `contract_version`: `"CE.1-r3"`
- `event`: `frame_selection` | `frame_conflict` | `frame_undetermined`
- `ruleset_hash`
- `frame_registry_hash`
- `input_hash`
- `context_hash` (includes user context and memory context)
- `state_hash` (includes previous frame, revision included)
- `allowed_memory_ref` (from adapter; `None` if not provided)
- `rules_fired`: list of `{id, priority, weight}`
- `allowed_frames_hash`
- `classifier`: `{version, params_hash, proposal}` or `None`
- `conflict`: bool
- `conflict_reason`: `hard_vs_classifier` | `hard_vs_hard` | `none`
- `resolution`: `hard_unique` | `hard_rule_override` | `soft_rule_accept` | `classifier_accepted` | `default` | `none`
- `previous_frame`: frame dict or `None`
- `selected_frame`: frame dict or `None`
- `revision`: integer
- `undetermined_reason`: string or `None`

Canonical serialization: `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.

The trace contains **no plaintext user input** and **no tokens**.

---

## 6. Memory isolation

- `memory_context` is placed in `effective_context["memory"]`, not flattened.
- Reserved key `"memory"` in the user context raises `ValueError`.
- `gate_available=False` raises `GateUnavailableError` (fail-closed).

This enforces the boundary:
IGL decides **what is allowed**; Cognitive Runtime decides **how it influences the frame**.

---

## 7. Memory Gate Adapter

Input: a dict-like Gate result with `accepted`, `withheld`, `constraints`.

Supported belief shapes:
- mock: `{"content": {"key": ..., "value": ...}}`
- real IGL Gate: `{"belief": {"value": {"key": ..., "value": ...}}, "trusted": bool, "applicable": bool}`

For the real shape, `trusted` and `applicable` must both be truthy.

Output:
- `AllowedMemory.memory_context`: dict of `key -> value` from accepted beliefs.
- `AllowedMemory.allowed_memory_ref`: canonical hash of accepted beliefs (order-independent).
- `MemoryAdapterDiagnostics`: `withheld_count`, `withheld_reasons`, `constraints_count`, `constraints`.

`withheld` and `constraints` are diagnostics only. They are **not** passed to Engine rules.

Mapping from raw memory keys to Engine boolean flags
(e.g. `preferred_reasoning=mathematics` -> `preferred_reasoning_math=True`)
is a **Cognitive Runtime** concern, not an adapter concern.
It lives in the test/application layer via an explicit table.

---

## 8. Tests

| Suite | File | Tests |
|---|---|---|
| Contract (T1–T18) | `tests/test_engine_contract.py` | 18 |
| Adapter unit | `tests/test_memory_adapter.py` | 8 |
| Two Johns (mock) J1–J4 | `tests/test_engine_contract.py` | 4 |
| Live IGL L1–L4 | `tests/test_integration_live.py` | 4 |
| Live Two Johns JL1–JL4 | `tests/test_integration_live_johns.py` | 4 |

Unit total: **100 passed**.
Live total: **8 passed** (requires running IGL server and user tokens).

---

## 9. What this contract does NOT cover

- Executing LLM inside the selected frame.
- Natural-language predicates (CE.3).
- Learning from consequences.
- Quality of reasoning.
- Consciousness.