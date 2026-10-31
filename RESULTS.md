# Results

## Test summary

| Suite | Tests | Status |
|---|---|---|
| Unit (contract, adapter, mock Johns) | 100 | passed |
| Live (IGL, L1–L4) | 4 | passed |
| Live (Two Johns, JL1–JL4) | 4 | passed |
| **Total live** | **8** | **passed** |

Live tests require a running IGL Memory server and valid user tokens.

## What was demonstrated

| Stage | Result |
|---|---|
| CE.1-r3 | Deterministic CognitiveFrame selection: HARD / SOFT / DEFAULT / UNDETERMINED, revision semantics, DecisionTrace |
| CE.2.1b | Adapter → Engine: memory in namespaced context, fail-closed on Gate unavailability, `allowed_memory_ref` in trace |
| CE.2.2 | Live IGL: record, correction, reject, forget → Gate → Adapter → Engine |
| CE.2.3 (mock) | Two Johns on mock memory: different memory → different frames |
| CE.2.3-live | Two Johns on real IGL: different users → different frames, same users → same frame, forget removes dependency, deterministic replay |

### Main experimental claim

> Given the same Cognitive Engine, the same operational context,
> and the same request, differences in the **allowed** long-term memory
> of IGL produced **reproducible** differences in the selected CognitiveFrame
> in the tested scenarios.

This is a narrow, testable claim. It is **not** a claim about reasoning quality,
consciousness, or superiority over existing agents.

### What was NOT demonstrated

- Improvement in reasoning quality.
- Superiority over a standard LLM agent.
- Self-acquisition of new strategies.
- Learning from consequences.
- Transfer of behavior across different LLMs.
- Subjective consciousness.
- Autonomous discovery of new modes of thinking.

**Important:** the memory-conditioned rules in the current experiments
are defined by the developer. The experiments demonstrate that **allowed memory
can change the selected frame**, not that the agent discovers new modes of
thinking on its own.

## Reproducibility

All unit tests are deterministic and require no external services.
Live tests require:
- running IGL Memory server (`IGL_BASE_URL`);
- user tokens (`IGL_USER_TOKEN_A`, `IGL_USER_TOKEN_B`);
- test database (do not run against production data).

`DecisionTrace` contains only hashes, fired rules, and frame metadata.
No plaintext user input, no tokens.