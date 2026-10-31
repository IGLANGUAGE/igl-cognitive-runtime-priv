# IGL Cognitive Runtime

Experimental architecture for context-dependent selection of a reasoning mode.

## What this is

A deterministic layer that selects a **CognitiveFrame** — a single consistent
configuration of register, coordinate system, reasoning strategy, and model tier —
**before** any LLM reasoning happens.

The frame selection is:

- deterministic (same inputs → same frame, same trace);
- independent of the executing LLM;
- conditioned on **allowed** long-term memory only;
- fully traceable through a structured `DecisionTrace`.

## Components

- **CognitiveFrame** — a consistent configuration:
  `(register, coordinate_system, strategy, model_tier, revision)`.
- **Cognitive Engine** — deterministic frame selector.
  HARD rules constrain the allowed set.
  SOFT rules rank it.
  A classifier may propose a frame inside the allowed set.
  Default and explicit `UNDETERMINED` handle the rest.
- **Memory Gate Adapter** — receives only what IGL Gate allowed
  (`accepted`), keeps `withheld` and `constraints` in diagnostics,
  and produces a namespaced `memory_context` for the Engine.
- **DecisionTrace** — structured event: fired rules, classifier proposal,
  conflict, resolution, previous/selected frame, revision, hashes.
  No plaintext user input, no secrets.

## What this is not

- Not an LLM.
- Not a memory store. IGL Memory is a separate system.
- Not a replacement for IGL Memory.
- Not a claim of consciousness.
- **Executing LLM is not connected yet.**
  The Engine selects a frame; what happens inside that frame is out of scope for CE.1–CE.2.

## Status

| Stage | Result |
|---|---|
| CE.1-r3 | Deterministic frame selection (HARD / SOFT / DEFAULT / UNDETERMINED) |
| CE.2.1b | Adapter → Engine, namespaced memory, fail-closed |
| CE.2.2 | Live IGL: correction / reject / forget → Gate → Engine |
| CE.2.3 (mock) | Different memory → different frames (mock) |
| CE.2.3-live | Two real IGL users → different frames (JL1–JL4) |

Tests: **100 unit passed, 8 live passed** (requires a running IGL server
and `IGL_USER_TOKEN_A` / `IGL_USER_TOKEN_B`).

See `CONTRACT.md` for the full contract and `RESULTS.md` for what was
and was not demonstrated.

## Requirements

- Python ≥ 3.11
- For live tests: running IGL Memory server + user tokens

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Run tests

Unit only (no server):
```bash
pytest -q
```

Live (requires IGL server, tokens in env):
```bash
$env:IGL_BASE_URL="http://127.0.0.1:8000"
$env:IGL_USER_TOKEN_A="..."
$env:IGL_USER_TOKEN_B="..."
pytest -q -m live
```

## License

Private. See LICENSE. Non-commercial use only until a public build is released.
