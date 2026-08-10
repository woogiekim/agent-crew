---
name: workflow-presets
description: Deterministic crew:run workflow preset classification and selection contract.
applies-to: run.md, workflow-preset-classifier.py, supervisor handoff
---

# Workflow Presets

`crew:run` can classify short user inputs into a workflow preset before the
normal supervisor pipeline starts. A preset is a thin preflight/postflight
wrapper. It must not replace the supervisor, select a hidden agent, mutate
external state, or reinterpret the user's original task text.

## Presets

| Preset | Use when | Execution shape |
|---|---|---|
| `default` | General implementation or fix request | Existing supervisor flow |
| `ticket-resolve` | Tracker issue id or issue-solving request | Issue intake, analysis adequacy check, implementation/review loop |
| `review-fix` | Review finding, feedback, or review follow-up | Compare review text to code, fix, test, and close residual risks |
| `debug` | Symptom, log, root cause, or diagnostic request | Evidence-first diagnosis before mutation |
| `bugfix` | Defect with reproduction/regression language | Reproduction/TDD bug fix loop |
| `parity` | Producer/consumer, legacy/new, migration, or contract parity | Scope the comparison, verify contract, then implement only inside scope |
| `closeout` | Summary, note draft, status, or handoff closeout | Read local state, draft factual summary, no remote write by default |

## Selection

The classifier is deterministic and conservative. It may auto-select only when
one high-confidence preset is matched and no conflict exists. Medium confidence,
low confidence, empty input, or multiple preset signals must route to the host's
structured choice capability before any workflow starts.

The fallback prompt is user-facing, not parser jargon:

```text
실행할 workflow를 선택해 주세요.

추천: review-fix
이유: review 신호가 review-fix 후보를 가리킵니다.
주의: 다른 workflow 신호도 감지되어 사용자 선택 후 진행해야 합니다.

1. review-fix
2. ticket-resolve
3. default
4. 취소
```

Use ordinary numbered list markers such as `1.`. Do not render circled number
symbols or machine-like labels such as `APPROVAL_GATE` in user-facing text.

When `crew:run` receives no task text, keep the existing "ask for task"
behavior but make the menu workflow-aware:

```text
무엇을 실행할까요?

1. Tracker issue id 입력
2. 최근 prompt 실행
3. 현재 작업 브랜치 기준으로 이어서 실행
4. 직접 작업 내용 입력
5. 취소
```

## State

After selection, record the decision in task context when a `TASK_DIR` exists:

```json
{
  "selected_workflow_preset": "ticket-resolve",
  "selection_source": "auto|user",
  "reason": "...",
  "signals": []
}
```

The selected preset is part of handoff context for the supervisor. The execution
must still delegate execution to `supervisor`; preset logic can add preflight
requirements, analysis checks, review loop instructions, and closeout guidance
only.

## Ticket Resolve

`ticket-resolve` must include an analysis adequacy check before implementation.
Its result is one of:

| State | Meaning |
|---|---|
| `READY` | The issue body/comments contain enough contract and scope detail to implement. |
| `NEEDS_ANALYSIS` | The issue is real but requires code or contract analysis before a plan is reliable. |
| `NEEDS_USER_INPUT` | Required product/scope data is missing and cannot be inferred safely. |
| `BLOCKED` | The tracker, repository, or required source of truth is unavailable. |

If the state is not `READY`, the supervisor records the gap and either performs
the required local analysis or stops for user input. It must not invent missing
tracker details.

## Review And Tracker Boundaries

`review-synthesis remains read-only`. Follow-up commands such as review note
posting, MR mutation, or tracker status changes are separate external writes.
Every external tracker write uses preview + exact approval before mutation.

Provider-native review must be exposed through provider-native review
capabilities or review-lens metadata. Core preset rules must not hardcode a
specific host's native review command; adapters provide capabilities and the
review workflow consumes those declarations.

## Exclusions

This workflow preset layer does not choose or mutate branch names. branch naming automation is out of scope for this change and remains governed by existing git or issue workflow rules.
