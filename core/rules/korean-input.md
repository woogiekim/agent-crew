# Rule: Korean Input Normalization

## When This Rule Applies

When any task description, `crew:run` argument, or orchestration instruction
contains Hangul characters (Unicode range U+AC00–U+D7A3 or Hangul Jamo/Compatibility
Jamo blocks).

## Trigger

Hangul characters detected in:
- Raw task strings passed to `crew:run`
- TASK values written to `pipeline.json` or `pipeline state`
- Task descriptions forwarded to any downstream agent (requirements, task-runner,
  planner, backend, frontend, designer, reviewer, devops)

## Normalization Step

**Before** writing the TASK to any agent prompt or `pipeline.json`, apply the
following normalization:

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
| `task-runner` | The delegated execution agent for a single task |
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
  task-runner can derive a concrete pipeline without further clarification.
- **Loss of implied scope**: Korean instructions often imply end-to-end scope
  (e.g., "배포해" implies build + test + push, not just a `git push`). Preserve that
  full scope in the normalized output.

## Where Applied

This normalization rule is enforced at three points in the execution pipeline:

| Location | When |
|---|---|
| `crew:run` Step 1 — Task collection | Before the raw input is normalized into the task list |
| `task-runner` Phase 0 — TASK variable | Before writing TASK to `pipeline.json` or any state file |
| Requirements agent task description | Before the TASK value is passed to the requirements interview |

## Examples

| Korean Input | Incorrect (literal) | Correct (intent-based) |
|---|---|---|
| 전반적으로 검토 | Comprehensively review | Perform a comprehensive review of the overall system |
| README 반영 | Reflect README | Reflect all changes in the README |
| 진행상황 보여주기 | Show progress | Display real-time task progress during execution |
| 승인 단계 추가 | Add approval step | Enforce an approval gate before execution begins |
| 코드 정리해 | Clean code | Refactor and clean up the codebase for maintainability and consistency |
| API 문서화 | Document API | Generate comprehensive API documentation covering all endpoints, request/response schemas, and authentication |
