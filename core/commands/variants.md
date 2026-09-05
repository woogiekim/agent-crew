# crew:variants — Candidate Variant Workflow

Manage candidate implementations created by `crew:run --variants N`.

```text
crew:variants collect
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
