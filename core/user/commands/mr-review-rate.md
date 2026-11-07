---
name: mr-review-rate
kind: review-lens
loaded_by: review-synthesis
lens_id: mr-review-rate
provider: gitlab
surface: command
read_only: true
mutates: false
requires_mr: required
requires_remote_read: required
requires_supervisor_context: false
default_enabled: true
timeout_seconds: 180
duplicate_group: mr-review-rate
---

# /mr-review-rate — GitLab MR Review Reflection Rate Audit

## 방법 비교와 트레이드오프

출력을 작성하기 전에 공통 지침 `core/rules/review-method-comparison.md`를 읽고 적용한다.
설치 환경에서는 `~/.agent-crew/rules/review-method-comparison.md`를 읽는다.
실제 방법명, 채택/권장/판단 보류 구분, 선택 이유, 얻는 점·감수할 점, 빈 줄과
`방법별 비교` 소제목, 후보별 설명·장단점, 확인 근거와 한계를 포함한다.
방법명이나 후보 개수를 고정하지 않는다. 방법 선택이 없는 항목에는 비교를 만들지 않는다.
이 형식은 보고서·분석·계획·인계·반영 노트의 서술에 적용하며, 원문 인용과 원시 증거,
프로토콜 필드, 상태·반영률·승인·실행 경계는 바꾸지 않는다.

## Purpose

Read the current GitLab MR notes and report how much of the review feedback has
been reflected in the local branch, commits, scope guard, and remote MR
description.

This command is read-only by default. It reports the reflection rate and the
remaining blocker. It does not implement review items or update remote MR state
unless the user separately approves a mutation.

## Trigger

- `/mr-review-rate`
- `/mr-review-rate !615`
- `crew:mr-review-rate`
- The user asks to read MR notes and report review reflection rate.

## Skip

- The user asks to implement review feedback. Use `crew:run` or a fix workflow.
- The user asks for a generic code review. Use the review workflow.
- The user asks to update MR description directly without a rate report.

## Inputs

- `MR_ID`: optional GitLab MR id or URL. If absent, infer from the current branch.
- `BASE_REF`: optional comparison base. Default: `origin/develop` when present.
- `SCOPE_GUARD`: optional project-specific forbidden paths or product areas.
- `OUTPUT_PATH`: optional markdown report path.

## Required Tools And Permissions

- Read: `glab mr note list`, `glab mr view`, `git status`, `git log`, `git diff`, `rg`.
- Optional read/local checks: `git diff --check`, syntax checks for changed helper scripts.
- Forbidden without explicit approval: `glab mr update`, `git push`, `git commit`, `git commit --amend`, `git rebase`, `git merge`.

## Flow

1. Delegate the audit to `mr-review-rate-auditor`.
2. The agent must read MR notes from GitLab in the current run.
3. The agent must split every reviewer request into atomic items.
4. The agent must compare each item against:
   - local diff and changed files;
   - local commit messages;
   - remote MR description/title/metadata when requested by review;
   - project scope guard.
5. The agent must classify each item as `DONE`, `LOCAL_DONE`, `PARTIAL`,
   `MISSING`, `BLOCKED`, or `NOT_APPLICABLE`.
6. The agent must report both:
   - local reflection rate;
   - full MR reflection rate, including remote MR description/metadata.
7. The agent must explain each meaningful reviewer item with implementation detail, including:
   - the reviewer request in preserved wording or faithful paraphrase;
   - the relevant code path, function, class, query, route, config, or document contract;
   - concise code excerpts or file references that prove the reflected behavior when available;
   - pseudocode that shows the intended behavior flow or decision branch;
   - why the evidence satisfies, partially satisfies, or fails the reviewer intent.
8. If the only missing item requires external write approval, the agent reports
   the exact remote action needed and stops.

## Contract-First Feedback Fidelity

The reflection rate is advisory, not the completion authority. Before reporting
a review item as reflected, preserve the original reviewer request, extract its
intent, identify affected contracts and side effects, and verify the item is
safe within the current scope.

For each review atom, include or derive these fields and surface them in the
human-readable report:

- intent and affected contract;
- disposition: `ACCEPT`, `ACCEPT_WITH_ADAPTATION`, `REJECT_METHOD_ONLY`,
  `DEFER`, or `REJECT`;
- safety labels: `contract-safe`, `parity-safe`, `scope-safe`,
  `side-effect-safe`;
- evidence or residual risk for labels that cannot be proven.

Do not let `LOCAL_REFLECTION_RATE`, `MR_REFLECTION_RATE`, or a high percentage
override contract, parity, scope, or side-effect gaps. A locally changed line,
passing test, or updated MR description is not enough when it does not prove
the reviewer's intended behavior, value, state, or side effect.

For review items that can change reachable behavior, persistence, events, logs,
network calls, generated output, UI state, producer/consumer parity, root cause,
or unused-code status, include caller graph status in the item explanation.
Use BFS inventory to map entrypoints, callers, callees, producers, consumers,
and configuration/registration edges, then use selective DFS deep dive only on
the risk-bearing path. `No references found` is a bounded search result, not a
global unused proof.

## Detailed Review Explanation

For every reviewer item classified as `DONE`, `LOCAL_DONE`, `PARTIAL`, `MISSING`, or
`BLOCKED`, include a detailed explanation unless the item is trivial metadata noise. The
explanation must help the operator understand what the review asked for and how the current
code does or does not satisfy it.

Use this structure inside the human-readable report:

````text
리뷰 항목 상세:
- 리뷰 요청: <reviewer request>
  판단: <DONE|LOCAL_DONE|PARTIAL|MISSING|BLOCKED|NOT_APPLICABLE>
  관련 코드: <path:symbol or path:line when verified>
  caller graph: <BFS inventory + selective DFS deep dive | partial | No references found | unknown | not_applicable>
  코드 근거:
  ```<language>
  <short excerpt or "현재 실행에서 확인된 코드 excerpt 없음">
  ```
  동작 수도코드:
  ```text
  <branch/flow/state-change pseudocode>
  ```
  설명:
  - <why this code/pseudocode satisfies or misses reviewer intent>
  - <remaining risk or remote MR gap, if any>
````

Rules for code and pseudocode:

- Quote only short excerpts needed to prove the review item; prefer file references when a
  long excerpt would be required.
- Do not invent code, tests, DB counts, or behavior. If the code path cannot be verified in
  the current run, say so and classify the item as `BLOCKED` or `MISSING`.
- Pseudocode must summarize the verified behavior, not the desired behavior, unless it is
  clearly labeled as a proposed follow-up.
- Keep the explanation proportional. Group identical low-risk items, but do not collapse
  distinct reviewer intents into one generic explanation.

## Output

Default user-facing output must be readable first. Keep the numeric meaning of
`LOCAL_REFLECTION_RATE` and `MR_REFLECTION_RATE`, but render them with natural labels in
the default report. Use machine-oriented field names only in an explicit raw/debug mode.

````text
MR 리뷰 반영률을 확인했습니다.

MR: !<id or unknown>
기준: <base ref or unknown>

로컬 반영률: <done>/<total-local> = <percent>
MR 전체 반영률: <done>/<total> = <percent>

반영 완료:
- <item> — <evidence>

로컬에는 반영됐지만 MR에는 아직 부족:
- <item> — <why only local is done>

일부만 반영:
- <item> — <remaining gap>

남은 항목:
- <item> — <missing evidence>

막힌 항목:
- <item> — <blocker>

범위 가드:
- <pass/fail>

리뷰 의도/계약 안전성:
- <item> — disposition=<ACCEPT|ACCEPT_WITH_ADAPTATION|REJECT_METHOD_ONLY|DEFER|REJECT>, contract-safe=<yes|no|unknown>, parity-safe=<yes|no|unknown>, scope-safe=<yes|no|unknown>, side-effect-safe=<yes|no|unknown>, residual risk=<none|details>

리뷰 항목 상세:
- 리뷰 요청: <reviewer request>
  판단: <DONE|LOCAL_DONE|PARTIAL|MISSING|BLOCKED|NOT_APPLICABLE>
  관련 코드: <path:symbol or path:line when verified>
  코드 근거:
  ```<language>
  <short excerpt or "현재 실행에서 확인된 코드 excerpt 없음">
  ```
  동작 수도코드:
  ```text
  <verified behavior flow or proposed follow-up when clearly labeled>
  ```
  설명:
  - <why evidence satisfies or misses reviewer intent>
  - <remaining risk or remote MR gap, if any>

확인한 명령:
- <commands run>

다음에 무엇을 할까요?

1. 부족 항목을 구현 흐름으로 넘기기
2. MR 설명 또는 note 갱신 프롬프트 만들기
3. 보고서만 유지
4. 종료
````

Selection handling:

- `1` must not edit files inside this read-only command. Return a separate execution prompt
  or logical intent for an implementation workflow.
- `2` prepares a prompt or logical intent for MR description/note follow-up without updating
  remote state inside this command.
- `3` returns the report only.
- `4` stops without further action.

Use ordinary numbered choices such as `1.` and do not use circled digit characters. If an
automation or parser needs machine-oriented output, expose it only in an explicit raw/debug
mode. If that mode is not implemented, keep the default output human-readable.

## Completion

The command completes when it has produced a numeric reflection report with
evidence and separated local completion from remote MR completion.
