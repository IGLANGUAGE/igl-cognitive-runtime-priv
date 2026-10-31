# IGL Cognitive Runtime — Contract

Status: CLOSED through CE.3
(engine, adapter, live IGL integration, deterministic predicates)

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
- `condition`: resolved through namespaced prefixes (CE.3):
  - `predicate:<name>` -> call registered predicate `name` on effective context
  - `flag:<name>` -> `effective_context[<name>] is True`
  - `memory:<key>` -> `effective_context["memory"][<key>] is True`
  - `memory.<key>` -> legacy CE.2.1b form, same as `memory:<key>`
  - plain key (no prefix) -> `effective_context[<key>] is True` (legacy flat flag)
- `frame`: partial frame (subset of `register`, `coordinate_system`, `strategy`)
- `scope`: string (documentation only at this stage)
- `weight`: positive integer, **SOFT only**
- `min_model_tier`: `small` | `medium` | `strong`, **HARD only**

Constraints:
- HARD: `frame` fields are exact; `min_model_tier` is a lower bound (not an exact value);
  `weight` must be `None`.
- SOFT: `frame` is a partial match; `weight` is a positive integer
  (float and bool rejected); `min_model_tier` must be `None`.

Predicates are **deterministic, pure functions** (`Context -> bool`):
no I/O, no LLM, no time, no randomness.
A predicate is pattern matching, not general natural-language understanding.

---

## 3. Selection

Given applicable HARD rules:

Before computing `ALLOWED`:

- Any HARD predicate error -> `UNDETERMINED` with reason `hard_predicate_error`.
  This takes priority over the success of any other HARD rule.
- Any SOFT predicate error -> rule is skipped, error is recorded
  in `predicates_evaluated`, selection continues.
- Unknown `predicate:<name>` in a rule at `Engine.__init__` -> `ValueError`.

1. Compute `ALLOWED`: all valid frames that satisfy all HARD rules.
   - exact match on `register`, `coordinate_system`, `strategy`;
   - `model_tier >= combined_min_model_tier`,
     where `combined_min_model_tier` is the maximum of applicable `min_model_tier` values.
2. If `ALLOWED` is empty -> `FRAME_CONFLICT`.
3. If `ALLOWED` has exactly one frame -> `hard_unique`. 
Additional `UNDETERMINED` reason:
- `hard_predicate_error` - a HARD predicate raised or returned non-bool.
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
- `predicate_registry_hash`: canonical hash of `{name: version}` (order-independent),
  or `None` if no predicates were registered.
- `predicates_evaluated`: list of `{name, version, result, error}` for each predicate
  actually called during selection. `result` is `bool` or `null`.
  `error` is `null` or `"PREDICATE_EVALUATION_FAILED"`.
  Full exception text is **not** recorded (may contain user data).

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
| Predicate registry P1/P2 | `tests/test_predicates.py` | 10 |
| Engine predicates P3/P4/P5 | `tests/test_predicates.py` | 4 |
| Natural-language P6a–P6e | `tests/test_builtin_predicates.py` | 6 |
| Live IGL L1–L4 | `tests/test_integration_live.py` | 4 |
| Live Two Johns JL1–JL4 | `tests/test_integration_live_johns.py` | 4 |

Unit total: **119 passed**.
Live total: **8 passed** (requires running IGL server and user tokens).

---

## 9. What this contract does NOT cover

- Executing LLM inside the selected frame.
- General natural-language understanding.
  CE.3 predicates recognise predefined patterns only (regex, structural),
  not semantic meaning.
- Learning from consequences.
- Quality of reasoning.
- Consciousness.