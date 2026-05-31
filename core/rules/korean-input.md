# Rule: Korean Input Normalization

## Contract — transform-and-deliver

The canonical contract for raw Korean (or any non-English) input is
**transform-and-deliver**: take the un-normalized question, transform it into a
canonical English orchestration instruction (NORMALIZED_TASK), and deliver
that normalized form to every downstream surface (supervisor, stage agent,
direct-agent path, host AI on the bare interactive path). The raw input is
preserved only as RAW_INPUT provenance in the `normalized_task.md` audit
artifact — it is never forwarded as canonical task text.

This is the **primary behavior** of the rule on every host (Claude, Codex,
Gemini, Cursor) and on every entry path (`crew:run`, `crew:agent`, bare
interactive answer). It is the AI-agnostic default — host-adapter hooks are
additive, never load-bearing.

Blocking raw Hangul (e.g., the `normalize-task-guard.sh` PreToolUse hook on
Claude) is a **last-resort backstop**, not the primary behavior. The backstop
fires only when an orchestrator failed to transform first; its reason text
must read as remediation that drives the transform-and-deliver path —
"run the input-normalizer transform (or inline equivalent), then re-issue
this call with the NORMALIZED_TASK form" — never as terminal rejection.

## When This Rule Applies

When any task description, `crew:run` argument, or orchestration instruction
contains Hangul characters (Unicode range U+AC00–U+D7A3 or Hangul Jamo/Compatibility
Jamo blocks).

## Trigger

Hangul characters detected in:
- Raw task strings passed to `crew:run`
- TASK values written to `pipeline.json` or `pipeline state`
- Task descriptions forwarded to any downstream agent (requirements, supervisor,
  planner, backend, frontend, designer, reviewer, devops)

## Normalization Step (transform-and-deliver)

**Before** writing the TASK to any agent prompt or `pipeline.json`, apply the
following transform-and-deliver normalization. The output is what every
downstream surface receives; the raw input is preserved only as provenance.

1. **Detect** — Scan the input string for Hangul characters. If none are present,
   skip normalization entirely.
2. **Interpret** — Identify the operational intent behind the Korean instruction.
   Do not translate word-for-word. Ask: what workflow outcome does the user expect?
3. **Rewrite** — Express the intent as a professional English orchestration
   instruction. Use terminology consistent with the existing agent and workflow
   architecture (see Vocabulary Reference below).
4. **Expand** — Where Korean shorthand omits context that is implied by domain
   knowledge, expand it into explicit operational behavior.
5. **Replace** — Use the rewritten English string as the canonical TASK value
   for all downstream agents and state files. The original Korean string must
   not appear in any agent prompt, `pipeline.json`, or `result.md`.

## Tone and Vocabulary

Normalized output must read as production-ready workflow instruction language:

- **Prefer**: clear execution-oriented phrasing, explicit workflow expectations,
  structured operational wording
- **Avoid**: awkward literal translation, missing implied workflow context, vague
  or conversational wording, untranslated orchestration concepts

Use terminology consistent with the agent-crew architecture:

| Term | Meaning |
|---|---|
| `supervisor` | The delegated execution agent for a single task |
| `pipeline` | The sequence of stages that execute a task |
| `stage` | A single agent invocation within a pipeline (e.g., backend, reviewer) |
| `handoff` | The transfer of output from one stage to the next |
| `approval gate` | A structured user-approval checkpoint before a destructive action |
| `requirements agent` | The agent that conducts the structured requirements interview |
| `planner` | The agent that decomposes a task into a pipeline plan |
| `resolver` | The agent that resolves merge conflicts after parallel task completion |
| `devops` | The stage agent responsible for deploy, push, and CI/CD actions |

## Shorthand Expansion Reference

The following table maps common Korean shorthand phrases used in this project to
their canonical English operational equivalents:

| Korean Input | Canonical English Instruction |
|---|---|
| 전반적으로 검토 | Perform a comprehensive review of the overall system |
| README 반영 | Reflect all changes in the README |
| 진행상황 보여주기 | Display real-time task progress during execution |
| 승인 단계 추가 | Enforce an approval gate before execution begins |
| 배포해 | Execute the deployment pipeline and push to the remote environment |
| 테스트 돌려 | Run the full test suite and report coverage results |
| 리뷰어 붙여 | Include a reviewer stage in the pipeline after implementation |
| 병렬로 실행 | Execute all tasks concurrently using parallel fan-out |
| 머지해 | Merge the feature branch into main after all stages complete |
| 롤백 | Roll back the deployment to the last known stable state |
| 다시 시도 | Retry the failed stage from its last checkpoint |
| 요구사항 정리 | Collect and formalize requirements through the structured interview process |

## What to Avoid

- **Literal translation artifacts**: Do not produce phrasing like "Reflect README"
  or "Add approval step" that maps Korean words one-to-one without conveying full
  operational meaning.
- **Untranslated concepts**: Do not pass Korean terms (배포, 검토, 파이프라인) into
  English-language agent prompts. All orchestration concepts must appear in English.
- **Vague phrasing**: Do not normalize to instructions like "do a review" or
  "update things." Every normalized instruction must be specific enough that a
  supervisor can derive a concrete pipeline without further clarification.
- **Loss of implied scope**: Korean instructions often imply end-to-end scope
  (e.g., "배포해" implies build + test + push, not just a `git push`). Preserve that
  full scope in the normalized output.

## Where Applied (transform-and-deliver entry paths)

The transform-and-deliver contract is the **primary behavior** on every
interactive orchestrator path in the system. The rule is AI-agnostic: it holds
on Claude, Codex, Gemini, and Cursor. Host hooks are capability-gated
augmentations whose only role is the **last-resort backstop** (block the call
when transform did not happen); the canonical enforcement is this rule file
itself, which drives the transform and the delivery of the normalized form.

| Location | When |
|---|---|
| `crew:run` Step 1 — Task collection | Before the raw input is normalized into the task list |
| `crew:agent` Step 5 — Direct-agent path | Before the named agent is invoked, even when no TASK_DIR exists |
| Bare interactive answer path | Before any host AI is asked the question (this is the path the user direction names explicitly) |
| `supervisor` Phase 0 — TASK variable | Before writing TASK to `pipeline.json` or any state file |
| Requirements agent task description | Before the TASK value is passed to the requirements interview |

## Entry-Path Scenarios — Transform Then Deliver

Issue #130 documented that interactive orchestrators could skip the
input-normalizer step entirely. The fix is the transform-and-deliver contract:
even when the full agent-crew pipeline does NOT run, the orchestrator MUST
transform the raw input and deliver the normalized form. Each entry path
follows the same primary behavior; only the persistence surface differs.

1. **`crew:agent` direct path** — `crew:agent` writes no `pipeline.json` and
   allocates no `TASK_DIR`. The contract still applies: the orchestrator
   transforms the input inline (per `core/rules/normalization-adapter.md`
   § How to Implement — inline mode), delivers the NORMALIZED_TASK to the
   named agent, and lands the audit artifact at
   `~/.agent-crew/state/{PROJECT_NAME}/normalized-tasks/{timestamp}.md`.

2. **Bare interactive answer path** — even when the user's input is going to
   be answered by the host AI inline (no `crew:run`, no `crew:agent`), if the
   input contains Hangul, the orchestrator transforms it to the canonical
   English form first and delivers that form as the question. The raw Korean
   string must not appear in the prompt sent to the host AI.

3. **Any downstream agent prompt** — once transformed, only the English
   `NORMALIZED_TASK` is delivered to planner, supervisor, stage agents, or any
   direct-agent spawn.

If an orchestrator surface fails to transform first, the capability-gated
backstop (on hosts with `hook_system: true`) blocks the call as the
**last-resort backstop**. The block reason names the transform-and-deliver
remediation so the operator can re-issue the call after running the transform.

## Audit Artifact — `normalized_task.md`

Every interactive orchestrator path MUST write an audit artifact that records
both the original raw input and the normalized English form. This is the
"provenance contract" — it makes the normalization step recoverable and
inspectable even when the full pipeline does not run.

### Location

| Path with TASK_DIR | Path without TASK_DIR (bare / `crew:agent`) |
|---|---|
| `{TASK_DIR}/context/normalized_task.md` | `~/.agent-crew/state/{PROJECT_NAME}/normalized-tasks/{ts}.md` |

`{ts}` is a UTC timestamp matching the existing `TASK_ID` convention
(`YYYYMMDD-HHMMSS`).

### Required fields

```text
RAW_INPUT: {original user input verbatim — Hangul or other source language preserved}
SOURCE_LANGUAGE: {detected language code or "unknown"}
NORMALIZED_TASK: {canonical English orchestration instruction}
NORMALIZED_AT: {UTC ISO-8601 timestamp}
NORMALIZED_BY: {host name — claude | codex | gemini | cursor | other}
PATH: {full source path — crew:run | crew:agent | bare-interactive | supervisor-phase-0}
```

The artifact is plain text (or Markdown frontmatter) so any host adapter can
write and read it without depending on a specific data format. The contract
is "both fields present, in that order, with NORMALIZED_TASK in English."

### Hard gate

The pipeline / direct-agent path MUST NOT proceed past the normalization step
until the audit artifact is on disk AND `NORMALIZED_TASK` has been confirmed
non-empty in English. Raw user input that requires normalization must never
appear as canonical downstream task text in:

- any agent prompt
- `pipeline.json` or any other state file
- `result.md`, `requirements.md`, or any downstream artifact

### Capability-gated augmentation (Claude PreToolUse hook — last-resort backstop)

On hosts that support `PreToolUse` hooks (`hook_system: true` —
`capabilities.json`), the `normalize-task-guard.sh` hook
(`core/hooks/normalize-task-guard.sh`) provides a mechanical defence-in-depth
**last-resort backstop**: it scans every Agent/Task tool call for raw Hangul
in `TASK:` / `REQUIREMENTS:` slots and blocks the call when no
`NORMALIZED_TASK:` provenance line is present. The block reason text is
remediation language that drives the transform-and-deliver path — it tells
the operator to run the input-normalizer transform and re-issue the call
with the NORMALIZED_TASK form, never that the call is terminally rejected.

The hook is registered through `adapters/claude/setup.sh`. Shell cannot
perform LLM translation, so the hook itself does not transform; the
transform lives in the orchestrator/agent layer (this rule file and
`core/rules/normalization-adapter.md`). On hosts without a hook surface
(Codex, Gemini, Cursor), this rule file is the load-bearing enforcement;
the hook is additive and runs only as the last-resort backstop.

## Examples

| Korean Input | Incorrect (literal) | Correct (intent-based) |
|---|---|---|
| 전반적으로 검토 | Comprehensively review | Perform a comprehensive review of the overall system |
| README 반영 | Reflect README | Reflect all changes in the README |
| 진행상황 보여주기 | Show progress | Display real-time task progress during execution |
| 승인 단계 추가 | Add approval step | Enforce an approval gate before execution begins |
| 코드 정리해 | Clean code | Refactor and clean up the codebase for maintainability and consistency |
| API 문서화 | Document API | Generate comprehensive API documentation covering all endpoints, request/response schemas, and authentication |
