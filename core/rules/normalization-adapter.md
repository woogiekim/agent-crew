# Normalization Adapter Contract

## Purpose

Defines the input/output contract that all host-adapter implementations of
input normalization must satisfy. The core pipeline (`crew:run` Step 1)
delegates to this contract; host adapters implement it.

This separation keeps the normalization rule provider-neutral (DIP): the core
workflow depends on the contract, not on any specific AI host implementation.

## Trigger Condition

Apply normalization when the raw task string:

- is not already a clear English operational instruction;
- contains non-English text;
- contains ambiguous conversational shorthand such as "go", "continue",
  "fix this", or "do the thing from before";
- relies on prior context that must be attached explicitly before downstream
  routing.

Korean/Hangul input is one required regression case, not the full design.

## Input / Output Contract

| Field | Description |
|---|---|
| `RAW_INPUT` / `RAW_TASK` | The original task string as supplied by the user, stored as provenance only |
| `SOURCE_LANGUAGE` | Detected language or `unknown` |
| `TRANSLATION_REQUIRED` | Whether translation to English is required |
| `NORMALIZED_TASK` | Canonical English orchestration instruction |
| `OBJECTIVE` | What must be achieved |
| `CONSTRAINTS` | User, system, and workflow constraints |
| `ACCEPTANCE_CRITERIA` | Observable completion checks |
| `MISSING_CONTEXT` | Unknowns or ambiguity that must not be guessed |
| `RISK_FLAGS` | Security, destructive, ambiguity, cost, or external dependency flags |
| `CONFIDENCE` | Normalization confidence |

## Normalization Steps

Apply the rules defined in `core/rules/korean-input.md` for Korean input and
the general prompt-quality compiler rules below for every input:

1. **Detect** — Identify source language and ambiguity.
2. **Translate** — Convert non-English input to English when needed.
3. **Interpret** — Identify the operational intent. Do not translate word-for-word.
4. **Rewrite** — Express the intent as a professional English orchestration instruction.
5. **Structure** — Add objective, scope, constraints, acceptance criteria,
   missing context, risk flags, and confidence.
6. **Replace** — Return `NORMALIZED_TASK` as the canonical downstream value.

## Output Requirements

- `NORMALIZED_TASK` must be English
- Must read as production-ready workflow instruction language
- Must be specific enough that a supervisor can derive a concrete pipeline
- Must record missing context instead of inventing requirements
- Must preserve raw input as provenance only, never as canonical downstream task text
- See `core/rules/korean-input.md` for vocabulary, tone, and shorthand expansion reference

## How to Implement

**When the host supports agent spawning (e.g., Claude Code):**
Delegate to the `input-normalizer` agent:
```text
RAW_INPUT: {original user input}
Apply input normalization and return the structured normalization contract.
```

**When the host does not support agent spawning (e.g., inline-only hosts):**
Implement the normalization steps inline before writing TASK to any state
file. The output must satisfy the same contract.

## Hard Gate

The pipeline orchestrator must not proceed past Step 1 until `NORMALIZED_TASK`
is confirmed. Raw user input that requires normalization must never appear as
canonical downstream task text in:
- Any agent prompt
- `pipeline.json` or any state file
- `result.md` or `requirements.md`
