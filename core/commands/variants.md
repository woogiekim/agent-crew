# crew:variants — Candidate Variant Workflow

Manage candidate implementations created by `crew:run --variants N`.

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

동시 변경 방지를 위해 variants 상태 변경은 `{STATE_DIR}/.variants.lock`, 반영은
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
완료 후 reviewer에게 완료된 후보별 커밋·실제 diff·테스트 로그·요구사항을 전달하여
비교 리뷰를 수행하고 `variant-review.md`에 추천 후보와 근거를 남긴다. 실패하거나
동일 SHA로 중복된 후보는 따로 표시한다. 추천은 선택 승인이 아니므로
selected_task_id를 자동 변경하거나 merge하지 않는다. CLI는 AI를 직접 호출하지 않는다.

## 중단 후 재개

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
