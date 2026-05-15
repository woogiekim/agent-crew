# Normalization Adapter Contract

## Purpose

Defines the input/output contract that all host-adapter implementations of
Korean Input Normalization must satisfy. The core pipeline (`crew:run` Step 1)
delegates to this contract; host adapters implement it.

This separation keeps the normalization rule provider-neutral (DIP): the core
workflow depends on the contract, not on any specific AI host implementation.

## Trigger Condition

Apply normalization when the raw task string contains one or more Hangul
characters (Unicode range U+AC00–U+D7A3, or Hangul Jamo / Compatibility Jamo
blocks).

If no Hangul is detected, pass the raw string through unchanged.

## Input / Output Contract

| Field | Description |
|---|---|
| `RAW_TASK` | The original task string as supplied by the user (may contain Hangul) |
| `NORMALIZED_TASK` | Canonical English orchestration instruction (no Hangul) |
| `RATIONALE` | One-line explanation of how the intent was interpreted |

## Normalization Steps

Apply the rules defined in `core/rules/korean-input.md`:

1. **Detect** — Confirm Hangul is present. If not, skip.
2. **Interpret** — Identify the operational intent. Do not translate word-for-word.
3. **Rewrite** — Express the intent as a professional English orchestration instruction.
4. **Expand** — Where Korean shorthand omits context implied by domain knowledge, expand it.
5. **Replace** — Return `NORMALIZED_TASK` as the canonical value.

## Output Requirements

- `NORMALIZED_TASK` must contain no Hangul characters
- Must read as production-ready workflow instruction language
- Must be specific enough that a supervisor can derive a concrete pipeline
- See `core/rules/korean-input.md` for vocabulary, tone, and shorthand expansion reference

## How to Implement

**When the host supports agent spawning (e.g., Claude Code):**
Delegate to the `korean-normalizer` agent:
```text
RAW_TASK: {original Korean string}
Apply core/rules/korean-input.md normalization and return NORMALIZED_TASK.
```

**When the host does not support agent spawning (e.g., inline-only hosts):**
Implement the five normalization steps inline before writing TASK to any state
file. The output must satisfy the same contract.

## Hard Gate

The pipeline orchestrator must not proceed past Step 1 until `NORMALIZED_TASK`
is confirmed. Raw Hangul must never appear in:
- Any agent prompt
- `pipeline.json` or any state file
- `result.md` or `requirements.md`
