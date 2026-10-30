# IGL Cognitive Runtime (private)

Deterministic cognitive frame selection for AI agents.
Contract-first. LLM-independent. Testable.

## Status

- Contract: **CE.1-r3** (CLOSED)
- Structures: in progress
- Tests T1-T18: in progress
- Engine: not started

## What this is

A separate layer above IGL Memory.

- **IGL Memory** answers: *what is the system allowed to remember and use?*
- **Cognitive Runtime** answers: *how should the system interpret the situation, given the experience it is allowed to use?*

The Cognitive Engine selects a `CognitiveFrame` — a single consistent configuration
(register, coordinate system, strategy, model tier) — before any LLM reasoning.

## What this is not

- Not an LLM.
- Not a memory store.
- Not a replacement for IGL Memory.
- Not a claim of consciousness.

## Contract

See `CONTRACT.md` (CE.1-r3). All tests T1-T18 must pass on stubs before the Engine is implemented.

## License

See `LICENSE`. Private. Non-commercial use only until a public build is released.
