# Normalization Adapter Contract

## Purpose — transform-and-deliver

The canonical contract is **transform-and-deliver**: take an un-normalized
question (non-English text, ambiguous shorthand, or conversational input) and
transform it into a canonical English orchestration instruction
(`NORMALIZED_TASK`); deliver that normalized form to every downstream surface
(supervisor, stage agent, direct-agent path, host AI). The raw input is
preserved only as `RAW_INPUT` / `RAW_TASK` provenance — it is never the
canonical downstream task text.

Transform-and-deliver is the **primary behavior** of the adapter on every
host and every entry path. Blocking raw non-English text (e.g., the
`normalize-task-guard.sh` PreToolUse hook on Claude) is a **last-resort
backstop**, not the primary behavior; the backstop fires only when an
orchestrator surface failed to transform first, and its reason text reads as
remediation that drives the transform-and-deliver path.

This file defines the input/output contract that all host-adapter
implementations must satisfy. The core pipeline (`crew:run` Step 1) delegates
to this contract; host adapters implement it. The separation keeps the
normalization rule provider-neutral (DIP): the core workflow depends on the
contract, not on any specific AI host implementation.

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

## Normalization Steps (transform-and-deliver)

Apply the rules defined in `core/rules/korean-input.md` for Korean input and
the general prompt-quality compiler rules below for every input. Steps 1–5
perform the **transform**; step 6 performs the **deliver**:

1. **Detect** — Identify source language and ambiguity.
2. **Translate** — Convert non-English input to English when needed.
3. **Interpret** — Identify the operational intent. Do not translate word-for-word.
4. **Rewrite** — Express the intent as a professional English orchestration instruction.
5. **Structure** — Add objective, scope, constraints, acceptance criteria,
   missing context, risk flags, and confidence.
6. **Deliver** — Return `NORMALIZED_TASK` as the canonical downstream value
   that every agent prompt, `pipeline.json`, and host AI question receives.
   The raw input is retained only as `RAW_INPUT` provenance in the audit
   artifact; it is never re-emitted as canonical task text.

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

## Audit Artifact Contract — `normalized_task.md`

Every interactive orchestrator path MUST persist a `normalized_task.md`
audit artifact recording both `RAW_INPUT` and `NORMALIZED_TASK` BEFORE the
downstream agent or host AI is invoked. The contract is provider-neutral:
it works on Claude, Codex, Gemini, and Cursor because it depends only on
the filesystem, not on any host-specific surface.

### Required fields

```text
RAW_INPUT: {original user input verbatim — preserved as provenance}
SOURCE_LANGUAGE: {detected language code or "unknown"}
NORMALIZED_TASK: {canonical English orchestration instruction}
NORMALIZED_AT: {UTC ISO-8601 timestamp}
NORMALIZED_BY: {host name — claude | codex | gemini | cursor | other}
PATH: {entry point — crew-run | crew-agent | bare-interactive | supervisor-phase-0}
```

### Location

| Context | Path |
|---|---|
| `crew:run` / supervisor pipeline | `{TASK_DIR}/context/normalized_task.md` |
| `crew:agent` direct path | `~/.agent-crew/state/{PROJECT_NAME}/normalized-tasks/{ts}.md` |
| Bare interactive answer (no TASK_DIR) | `~/.agent-crew/state/{PROJECT_NAME}/normalized-tasks/{ts}.md` |

`{ts}` matches the existing `TASK_ID` convention (`YYYYMMDD-HHMMSS`).

### Where the contract is enforced

The audit artifact gate runs at three orchestrator entry points. Every
host adapter MUST honour all three; only the surface (Step 1 / Step 5 / bare
answer) differs.

| Entry point | Enforcement site | What MUST happen |
|---|---|---|
| `crew:run` | `core/commands/run.md` Step 1 — Input Normalization | Write `{TASK_DIR}/context/normalized_task.md` before Step 2 (state init). |
| `crew:agent` (direct) | `core/commands/agent.md` Step 5 — Input normalization | Write `~/.agent-crew/state/{PROJECT_NAME}/normalized-tasks/{ts}.md` before Step 6 (visibility line) and Step 7 (invoke the agent). |
| Bare interactive answer | This rule file (host-agnostic) | Before the host AI is asked the question, normalize inline and write `~/.agent-crew/state/{PROJECT_NAME}/normalized-tasks/{ts}.md`. |

This explicit triple-coverage exists because the user direction is verbatim:
"에이전트크루 파이프라인이 실행 안되더라도 정규화해서 코덱스나, 클로드, 제미나이,
커서 이런 ai 들에게 질문하게 하는것으로 동작했으면 한다." Normalization MUST
happen even when the full crew pipeline does NOT run.

## Hard Gate

The pipeline orchestrator must not proceed past Step 1 until `NORMALIZED_TASK`
is confirmed AND the `normalized_task.md` audit artifact has been written.
Raw user input that requires normalization must never appear as canonical
downstream task text in:
- Any agent prompt (TASK:, REQUIREMENTS:, CHANGE REQUEST: slots)
- `pipeline.json` or any state file
- `result.md` or `requirements.md`
- The prompt sent to any host AI (Claude, Codex, Gemini, Cursor)

### Capability-gated augmentation (Claude PreToolUse hook — last-resort backstop)

Hosts that advertise `hook_system: true` in `capabilities.json` (currently
Claude) install a mechanical PreToolUse guard that re-checks every Agent /
Task tool call for raw non-English content in TASK-shaped slots. The hook
runs as the **last-resort backstop** for the transform-and-deliver contract:
it fires only when an orchestrator surface failed to transform first, and
its reason text reads as remediation that drives the transform — it tells
the operator to run the input-normalizer transform and re-issue the call
with the NORMALIZED_TASK form, never that the call is terminally rejected.

The hook implementation lives at `core/hooks/normalize-task-guard.sh` and is
registered through `adapters/claude/setup.sh`. It exempts the
`input-normalizer` and `korean-normalizer` agents and accepts an explicit
escape hatch via `AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=1`. Shell cannot
perform LLM translation, so the hook itself does not transform — the
transform lives in the orchestrator/agent layer (this rule and
`core/rules/korean-input.md`). The hook is defence-in-depth — the canonical
enforcement remains this rule and the rules it references; the hook does
NOT replace the inline normalization step. On hosts without a hook surface
(Codex, Gemini, Cursor), this rule file is the load-bearing enforcement,
which means the entire transform-and-deliver primary behavior is delivered
by the rule prose itself.
