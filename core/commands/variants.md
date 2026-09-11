# crew:variants — Candidate Variant Workflow

Manage candidate implementations created by `crew:run --variants N`.

아래 기존 select/apply 및 Markdown 리뷰 설명은 v1 계약이다. 승인된 v2 세션은
`v2 자동 연속 실행` 절을 따라 분석/종합/독립 검증까지 이어간다.

```text
crew:variants collect
crew:variants collect --wait --timeout 600
crew:variants resume --timeout 600
crew:variants review --claim INPUT_HASH
crew:variants review --complete TOKEN --report PATH
crew:variants review --release TOKEN
crew:variants select TASK_ID
crew:variants apply
crew:variants apply --target BRANCH --dry-run
crew:variants apply --target BRANCH --confirm PLAN_HASH
```

`crew:variants collect` reads the active variants `session.json`, summarizes
completed candidate `result.md` files, writes `variant-summary.md`, keeps
`selection_status: "pending"`, and stops before any merge or branch mutation.

`crew:variants select TASK_ID` records the chosen candidate in `session.json`
with `selection_status: "selected"` and `selected_task_id`. It does not mutate
branches or apply the implementation.

`crew:variants apply` prints the approval-bound apply plan for the selected
candidate. It does not mutate branches by itself; applying the implementation
requires an explicit branch operation whose target, reversibility, and approval
contract are clear.

`crew:variants apply --target BRANCH --dry-run`은 선택된 후보와 로컬 대상
브랜치를 검증하고, 커밋 SHA, 후보 변경 범위, 병합 충돌 여부를 출력한다.
후보는 `completed` 상태여야 하며 원본과 같은 저장소의 독립 worktree에서
기록된 후보 브랜치를 checkout하고 있어야 한다. 원본과 후보에 미커밋 변경이
있거나 사용자 정의 merge driver가 설정되어 있으면 중단한다.

충돌 계산은 임시 객체 디렉터리에서 수행한다. 브랜치, index, 작업 파일과
세션 상태는 변경하지 않는다. 종료 코드는 충돌 없음 `0`, 충돌 있음 `1`,
검증 또는 실행 실패 `2`다. 충돌 없음은 빌드나 테스트 성공을 의미하지 않는다.
`--target`과 `--dry-run`은 함께 지정해야 한다. 옵션 없는 `apply`는 기존처럼
선택 정보만 출력한다.

`crew:variants apply --target BRANCH --confirm PLAN_HASH`는 미리보기에서 출력한
`plan_hash`를 승인하여 선택 후보를 로컬 merge commit으로 반영한다.
`--dry-run`과 `--confirm`은 동시에 사용할 수 없다. 해시는 세션 원문과 선택 정보,
후보와 대상 커밋, 경로, 예상 결과 tree, 런타임, Git 설정 및 merge 관련 hook에
묶인다. 변경되면 새 미리보기를 확인하고 새 해시로 승인해야 한다.

원본 worktree에는 대상 브랜치가 이미 checkout되어 있어야 한다. 명령이 브랜치를
자동 전환하지 않는다. 충돌이 예상되면 반영 전에 중단한다. `git merge --no-ff
--strategy=ort`로 검증한 후보 SHA를 반영하며, Git hook과 서명 설정을 유지한다.
원격 push는 수행하지 않는다. 충돌 검사와 해시 검증은 코드 리뷰나 테스트를 대체하지 않는다.

실행 전 `apply_status: applying`과 `apply_record`를 원자적으로 기록한다. 성공하면
`apply_status: applied`, `applied_branch`, `applied_task_id`, `applied_at`과
`apply_record.applied_commit`을 기록한다. 동일 계획을 다시 실행하면 대상 커밋과
선택 정보를 확인하여 `already_applied`로 종료한다.

Git 명령이 실패하면 `failed` 또는 `conflict`와 오류를 기록하고 종료 코드 `2`로
중단한다. 작업 파일이나 Git 상태를 자동 reset/abort하지 않는다. 원본의
`git status`를 확인하고, 진행 중인 병합을 취소하려면 `git merge --abort`로 복구한다.
이전 대상 커밋과 깨끗한 작업 상태로 복구한 뒤 새 `--dry-run`과 `--confirm`으로
재시도할 수 있다. 이전 실패 기록은 `apply_history`에 보존한다.

동시 변경 방지를 위해 native run과 variants 상태 변경은 공통 `{STATE_DIR}/.variants.lock`, 반영은
Git common directory의 `crew-variants-apply.lock` 디렉터리를 사용한다.
프로세스 강제 종료로 잠금이 남으면 실행 중인 프로세스가 없음을 확인하고 Git 상태를
복구한 다음 해당 잠금 디렉터리를 제거한다. 다른 Git 도구를 통한 동시 편집은 피한다.

Use `crew:variants collect` for candidate collection.

`crew:variants collect --wait`는 모든 후보의 result.md가 completed/blocked/cancelled가
될 때까지 기다린 뒤 비교표를 출력한다. 기본 제한 시간은 600초, 조회 간격은 1초다.
`--timeout SECONDS`와 `--interval SECONDS`로 조정한다. 제한 시간 초과는 종료 코드
`3`과 `collection_status: timed_out`을 반환하며 미완료 후보를 완료로 처리하지 않는다.
대기 중 세션 또는 후보 목록이 바뀌면 종료 코드 `2`로 중단한다.

호스트의 `crew:run --variants` orchestrator는 모든 supervisor를 병렬 위임한 뒤
이 완료 장벽을 자동 실행한다. 사용자의 추가 collect 요청을 기다리지 않는다.
v1 완료 후 reviewer에게 완료된 후보별 커밋·실제 diff·테스트 로그·요구사항을 전달하여
비교 리뷰를 수행하고 `variant-review.md`에 추천 후보와 근거를 남긴다. 실패하거나
동일 SHA로 중복된 후보는 따로 표시한다. 추천은 선택 승인이 아니므로
selected_task_id를 자동 변경하거나 merge하지 않는다. CLI는 AI를 직접 호출하지 않는다.

## v2 자동 연속 실행

산출물 기준 경로는 `session.variants_dir`이며 이 필드가 없는 기존 v1 및 구형 v2
fixture는 `STATE_DIR`를 사용한다. 신규 native v2는
`STATE_DIR/variants/<session_id>`를 기록한다. CLI의 `VARIANTS_DIR` 출력과
resume의 `variants_dir`를 확인하여 handoff에 고정된 출력 경로를 전달한다.
`variant-summary.md`, `variant-review-state.json`을 비롯한 receipts,
`variant-review.json`, `variant-review.md`, `variant-synthesis-state.json` 및
종합 task는 이 기준 경로 아래에 저장한다. `STATE_DIR/session.json`은 계속 루트에
있으며 후보 tasks와 세션 status를 관리한다. `.variants.lock`도 루트 공통 잠금이다.

reviewer의 출력은 후보 task_dir 밖, 위 세션 경로의 지정된 산출물에 고정한다.
후보 task_dir의 기존 증거는 읽기만 하며 출력 경로로 재사용하지 않는다.
활성 v2가 있으면 새 run의 덮어쓰기는 금지하며 resume을 먼저 수행한다.
완료 후 새 세션은 새 session_id 경로를 사용하고 이전 산출물은 그대로 보존한다.

응답의 `input_hash=current`는 현재 입력 해시다. `synthesis_input_hash`는 기존 receipt가
보유한 입력 해시로 둘을 구분한다. stale receipt 해시를 현재 input_hash로 덮어쓰거나
새 prepare/claim에 현재 해시 대신 사용하지 않는다.

`variants_workflow_version: 2`, `outcome_mode: synthesis`가 포함된 초기 승인 그래프는
구현 -> 분석/비교 -> 종합 -> 독립 검증까지 포함한다. 호스트 orchestrator는
추가 사용자 요청 없이 다음 단계를 이어간다. native CLI는 AI를 실행하지 않는다.
CLI가 내놓는 handoff/next_action은 실행 지시 정보이며 실제 위임은 승인된 호스트가 한다.
새 후보와 종합 handoff의 `pipeline.json`은 `planning_required: true`인 임시 상태다.
supervisor는 `supervisor-start-mode.py`의 fresh 판정에 따라 실제 analyst 계획부터 수행한다.
파일이 있다는 이유로 승인된 실행 계획의 resume으로 처리하거나 직접 구현하지 않는다.
실제 계획으로 교체되고 quality-plan gate를 통과한 뒤에만 구현 단계로 진입한다.

### 중첩 child 호출을 지원하지 않는 호스트

승인된 supervisor 세션에 child 도구가 없고 부모 orchestrator에만 도구가 있으면,
부모는 동일 논리 그래프의 호출 중계만 수행할 수 있다. supervisor의 inline 구현이나
analyst/test-writer/reviewer 생략으로 대체하지 않는다. 앱의 `create_thread`로 사용자
작업을 생성하는 우회도 금지한다. 부모에게도 적합한 도구가 없으면 정확한 blocker를 반환한다.

supervisor는 자신의 task context에 `child-request.json`을 작성하고
`WAITING_FOR_CHILD`를 반환한다. 요청에는 고유 `request_id`, 승인된 `role`,
`definition_path`, 고정 `project_root`, `task_dir`, 원문과 권한을 보존한 `prompt`를 담는다.
부모는 기존 승인 그래프/역할/경로와 대조하고 실제 호출 전에 요청 식별자를 기록한다.
호출 후 실제 host ID를 같은 요청에 연결하여 supervisor에 전달한다. 호출 성공 여부가
불명확하면 살아 있는 실행부터 확인하고 중복 위임하지 않는다. 새 논리 역할이나 범위가
필요하면 새 계획/승인을 받는다. 이 중계는 역할별 모델/권한을 임의 변경할 권한이 아니다.

child는 지정된 역할과 skill을 직접 로드하고 자기 산출물만 작성한다. supervisor는
실제 응답과 검증 결과를 확인한 뒤 다음 승인 노드를 요청한다. TDD의 RED 이후 GREEN,
Refactor와 독립 reviewer 순서를 유지한다. 동시성 제한 때문에 같은 그래프를 순차
실행할 수 있지만 역할을 합치거나 성공 증거를 대필하지 않는다. 부모는 요청/응답과
실제 host ID를 task-local dispatch 기록에 남기고 종료된 child만 정리한다.

### 초기 차단 조건

nonGit은 읽기 전용 v2도 Git이 필수이므로 handoff 생성 전에 exit 3으로 차단한다.
구현 작업 역시 mutating parallel launch 전에 차단한다.
Git 저장소에서도 `--read-only --variants N`은 worktree 생성 및 Git 변이를 방지하기
위해 handoff와 worktree 생성 전에 exit 3으로 초기에 거부한다.
읽기 전용 작업을 종합 구현 승인으로 확대하지 않는다.

`resume`의 `next_action`에 따른 동작:

초기 세션은 `workflow_status=implementing`이다. `resume`와 `manage_synthesis`는
반환한 next_action을 workflow_status에 기록한다. `session.status=completed`는
`ready_for_apply`에서만 설정한다. 전부 실패한 `no_completed_candidates`,
`synthesis_failed`, `blocked`는 session.status를 blocked로 기록한다. 이를 성공 완료나 계속 실행 중인 후보로
오해하지 말고 실패 이유를 보고한다. 아래 분석/비교 같은 설명은 사람이 읽는 단계명이며
별도의 런타임 상태 토큰을 만들지 않는다.

- `review_required`: 아래 claim/bind 절차로 실제 비교 reviewer를 위임한다.
- `review_in_progress`: 기존 host ID의 실행 상태를 확인한다. 중복 위임하지 않는다.
- `synthesis_required`: 승인된 종합 supervisor를 별도 worktree에 연결한다.
- `synthesis_in_progress`: 기존 종합 실행을 기다리거나 동일 handoff를 복구한다.
- `synthesis_failed`: 실패 이유를 보고하고 종료된 실행을 계속 대기하지 않는다.
  자동 재위임하지 않는다. 재시도는 원인과 기존 실행 종료를 확인한 뒤 명시적 복구로 진행한다.
- `validation_required`: 최종 독립 reviewer를 실행하고 결함은 기존 quality-loop로 수리한다.
- `blocked`: 예산 소진 또는 해결되지 않은 차단 사유를 보고하고 자동 재시도하지 않는다.
  validation_required로 해석하거나 release/prepare로 예산 제한을 우회하지 않는다.
- `ready_for_apply`: 최종 구현과 검증 결과를 제시하고 별도 원본 반영 승인을 기다린다.
- `no_completed_candidates`: 실패 이유를 보고한다. 전부 실패를 성공 리뷰로 만들지 않는다.
- stale/입력 해시 변경: 기존 완료 결과를 재사용하지 않는다. 살아 있는 실행부터 확인하고
  승인된 입력/그래프에 맞춰 영향 단계와 후속 결과를 재검토한다.

v1의 `review_complete` 및 Markdown 완료는 v2 완료 증거로 승격하지 않는다.
v2에서는 비교 완료 뒤 종합으로 진행하며 `selected_task_id`를 자동 선택하지 않는다.
가짜 host ID, 가짜 receipt, prompt-only 완료를 금지한다. ID 문자열의 bind나
구조 검사 통과만으로 실제 AI 실행과 의미 품질을 증명했다고 보고하지 않는다.
실제 호스트 실행 이력, 코드 분석, 실행 로그와 독립 reviewer 판단을 확인한다.

### v2 리뷰 실행

1. `crew variants review --claim INPUT_HASH`로 현재 입력에 대한 token을 얻는다.
2. 최초 승인 그래프의 `MODE: variant-analysis` 및 `MODE: variant-comparison`
   reviewer를 호스트에서 실행한다. 원문, 고정 base/후보 SHA, 공통 행동 단위,
   실제 diff와 호출 경로, 테스트 로그를 전달한다. 기존 후보 reviewer 분석은 검증 후 재사용한다.
3. `crew variants review --bind TOKEN --host-id HOST_AGENT_ID`에
   호스트가 반환한 실제 agent ID를 전달한다. bind 대상은 canonical JSON의
   semantic_review를 판정한 비교 reviewer이며 `semantic_review.reviewer_id`와 일치해야 한다.
4. 실행 종료와 실제 산출물을 확인한 뒤
   `crew variants review --complete TOKEN --report CANONICAL_JSON`으로 등록한다.
   `variant-review.json`이 정본이고 `variant-review.md`는 렌더링 결과다.
   스키마는 `core/schemas/variant-review.schema.json`, 예제는
   `tests/fixtures/variants/review-v2.json`이다. 예제 SHA/ID는 실제 증거로 대체한다.

비교 reviewer는 read-only이며 지정 리뷰 산출물 외에 후보 구현/증거를 수정하지 않는다.
모든 후보 × 공통 행동 단위 구현의 육하원칙, 장단점, 비교 및 decision별 별도 육하원칙을
작성한다. 실패 후보는 진단 사유를 남기고 채택하지 않는다. 단일 유효 후보의 비교 한계,
동일 SHA, unknown과 N/A 사유를 표시한다. 의미상 불충분하면 needs_changes로 반환한다.
기존 reviewer 실행 종료를 확인한 뒤에만 `crew variants review --release TOKEN`으로
해제한다. release는 AI를 종료하지 않으며 새 claim 전에 기존 실행을 중복 생성하지 않는다.

### v2 종합 실행

1. `crew variants synthesize --prepare INPUT_HASH`로 고정 base의 별도 종합
   worktree와 token/handoff를 준비한다. 준비 자체는 AI 실행이 아니다.
2. 승인된 종합 supervisor/implementation agent를 반환된 PROJECT_ROOT와 handoff로
   실행한다. supervisor 호출은 `MODE: supervisor`, `VARIANT_SYNTHESIS: true`를
   전달한다. 종합 구분자를 supervisor의 MODE 대신 사용하지 않는다.
   후보 전체 merge를 수행하지 않는다. 후보와 원본은 보존한다.
3. `crew variants synthesize --bind TOKEN --host-id HOST_AGENT_ID`에
   호스트가 반환한 실제 agent ID를 연결한다. 이 ID는 RESULT_JSON의 implementer_id를
   소유한 실행과 같아야 한다. supervisor와 child ID를 임의로 바꾸어 쓰지 않는다.
4. 구현 실행 종료 후 아래 독립 검증을 수행하고 실제 결과를 수집한 뒤
   `crew variants synthesize --complete TOKEN --result RESULT_JSON`으로 등록한다.
   complete 호출만으로 성공을 가정하지 않고 반환 status/next_action을 확인한다.

후보 구현자와 종합 구현자는 기존 supervisor의 `Red -> Green -> Refactor`를 수행한다.
기존 실행 종료를 확인한 경우에만 `crew variants synthesize --release TOKEN`으로
해제한다. 자동 만료나 살아 있는 agent의 중복 위임은 허용하지 않는다.

### v2 독립 검증

호스트는 `MODE: final`, `VARIANT_SYNTHESIS: true`로 최종 독립 reviewer를 위임한다.
실제 `reviewer_id != implementer_id`여야 한다. 최종 SHA의 공통 acceptance,
decision_id별 최종 diff/심볼/검증 매핑, 조합 경계 회귀와 단위별 육하원칙을 확인한다.
reviewer는 read-only이며 실제 실행 로그/코드를 검토하고 지정 검증 산출물만 작성한다.
가짜 로그/fixture receipt, 자체 승인 문구, prompt-only 완료로 대체하지 않는다.

needs_changes는 기존 종합 구현자에게 검증된 finding을 돌려보내고
`Red -> Green -> Refactor` 수리 및 독립 재검증을 수행한다. 예산 소진/미해결이면
blocked이며 ready로 표시하지 않는다. 범위/그래프/승인 변경은 새 계획을 요구한다.
RESULT_JSON은 현재 종합 런타임 계약에 따라 commit, implementer_id, reviewer_id,
verdict, unresolved_findings, 공통 acceptance의 command/log/실제 결과,
decision_results와 최종 단위 analysis를 담는다. 독립 reviewer가 실제 판정한 결과를
호스트가 전달하며 구현자에게 reviewer_id나 판정을 만들어 쓰게 하지 않는다.

공통 acceptance 외에 채택한 장점 각각의 `decision_results[].validation`은
`passed: true`, `command`, `log`를 필수로 갖는다. 최상위 `composition_checks`는
`name`, `passed: true`, `command`, `log`를 갖는 비어 있지 않은 목록이다.
채택 요소와 조합 회귀를 실제 실행하고 모든 log는 synthesis task_dir 내부 실제
파일로 남겨 SHA-256에 바인딩한다. 공통 acceptance 성공으로 이 검증을 대신하지 않는다.

`ready_for_apply`에서 비교·채택 근거, 최종 diff/SHA, 실제 테스트, 독립 검토와 남은
한계를 제시한다. `apply --artifact final`은 최종 산출물을 대상으로 하는 별도 승인
인터페이스다. 런타임 지원을 확인하고 지원 전에는 실행하지 않는다. legacy 후보로
몰래 우회하거나 selected_task_id를 바꾸지 않는다. v2 후보 apply 우회는 금지하며
`--artifact final`만 사용한다. 자동 merge, push, deploy는 금지한다.
초기 로컬 종합 승인은 원본 반영 승인이 아니다.

## v1 중단 후 재개


`crew:variants resume`는 현재 세션의 기존 후보를 재수집하고 미완료 후보만 기다린다.
기본 timeout/interval과 종료 코드는 `collect --wait`와 같다. 새 task, branch,
worktree, supervisor를 생성하지 않는다. 대기 중 부모가 종료되어도 같은 명령으로
이어간다. 살아 있는 후보에는 다시 위임하지 않는다. 호스트 실행이 끊긴 후보는
기존 task ID와 handoff 및 승인된 계획으로 복구해야 하며 이 CLI가 재실행하지 않는다.
잠금이 남았으면 앞서 설명한 실행 상태 확인·수동 복구 절차를 먼저 따른다.

수집 완료 시 JSON의 `next_action`에 따라 호스트 orchestrator가 이어간다:

- `review_required`: 출력된 `input_hash`로 `crew variants review --claim INPUT_HASH`를
  먼저 실행한다. 성공한 한 호출만 `token`을 받는다. 그 뒤 reviewer를 위임한다.
- `review_in_progress`: 기존 리뷰를 기다리거나 해당 호스트 실행을 이어간다.
  입력이 변경되어도 자동으로 두 번째 reviewer를 만들지 않는다.
- `review_complete`: 같은 입력으로 완료한 `variant-review.md`를 재사용하고 선택을 기다린다.
- `no_completed_candidates`: 성공 후보가 없으므로 실패 사유를 보고하고 멈춘다.

Reviewer에는 `inputs`의 후보별 실제 커밋과 base 커밋, diff, task 원문/요구사항,
테스트 증거를 전달한다. 리뷰는 task 증거를 수정하지 않고 별도 초안에 작성한다.
완료 후 `crew variants review --complete TOKEN --report PATH`로 등록한다.
이 명령은 고정 경로 `variant-review.md`에 보고서를 원자적으로 저장하고
`variant-review-state.json`에 입력 해시·토큰·보고서 해시·완료 상태를 기록한다.
CLI의 완료 등록은 리뷰 품질을 판정하거나 실제 AI 실행을 증명하지 않는다.

입력 해시는 세션 ID/원문, 후보 메타데이터, task 바로 아래 파일과 context 하위
파일의 내용, 완료 후보의 실제 HEAD와 원본 HEAD를 포함한다. 완료 후보는 원본과
같은 저장소의 깨끗한 독립 worktree 및 기록된 브랜치여야 한다. 외부 증거는 먼저
task/context에 보존한다. 입력 변경 시 오래된 토큰의 완료 등록을 거부하며 완료
리뷰도 재사용하지 않는다. 손상된 상태 파일은 새 리뷰로 간주하지 않고 중단한다.

부모 또는 reviewer가 종료된 경우 **이전 reviewer가 더 이상 실행되지 않음을 먼저
확인한 뒤** `crew variants review --release TOKEN`으로 실행 기록을 해제하고
resume → claim 순서로 재시도한다. release는 AI를 취소하지 않으며 자동 만료도 없다.
새 claim은 새 토큰을 발급하고 이전 기록을 history에 보존한다. 보고서 저장 직후
프로세스가 끊겨 상태가 running이면 같은 토큰으로 complete를 다시 시도할 수 있다.
기존 토큰 없는 보고서만 있으면 완료 증거로 신뢰하지 않고 비교 리뷰를 다시 수행한다.
어느 재개 단계도 후보 선택이나 apply 승인을 자동 변경하지 않는다.
