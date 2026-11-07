---
name: generic-review
kind: review-lens
loaded_by: review-synthesis
lens_id: generic-review
provider: local
surface: command
read_only: true
mutates: false
requires_mr: none
requires_remote_read: none
requires_supervisor_context: false
default_enabled: true
timeout_seconds: 300
duplicate_group: generic-review
---

# /generic-review — 일반 코드리뷰 렌즈 (`review` 명령 래퍼)

## 방법 비교와 트레이드오프

출력을 작성하기 전에 공통 지침 `core/rules/review-method-comparison.md`를 읽고 적용한다.
설치 환경에서는 `~/.agent-crew/rules/review-method-comparison.md`를 읽는다.
실제 방법명, 채택/권장/판단 보류 구분, 선택 이유, 얻는 점·감수할 점, 빈 줄과
`방법별 비교` 소제목, 후보별 설명·장단점, 확인 근거와 한계를 포함한다.
방법명이나 후보 개수를 고정하지 않는다. 방법 선택이 없는 항목에는 비교를 만들지 않는다.
이 형식은 보고서·분석·계획·인계·반영 노트의 서술에 적용하며, 원문 인용과 원시 증거,
프로토콜 필드, 상태·반영률·승인·실행 경계는 바꾸지 않는다.

## Purpose

`review-synthesis` 가 발견할 수 있는 **agent-crew 소유의 일반 코드리뷰 렌즈**다.
리뷰 로직을 자체 구현하지 않고, agent-crew 사용자 레이어의 `/review` 커맨드에
위임한다. 이 파일이 소유하는 것은 **렌즈 메타데이터와 결과 매핑 규약**뿐이다.

이 래퍼는 일반 리뷰의 렌즈 메타데이터와 결과 매핑을 소유한다. 실제 리뷰 절차는
`review` 명령 원본에서 관리하며 중복 구현하지 않는다.

## Delegation Target

- 위임 대상: `/review` — `~/.agent-crew/commands/review.md`
- 저장소 원본: `core/user/commands/review.md`
- 대상 선택, base 브랜치 자동 감지, 리뷰 포커스 체크리스트, 서브에이전트 기동은
  **전부 원본의 책임**이다. 이 파일에 그 내용을 복제하지 않는다. 복제하면
  원본이 바뀔 때 조용히 갈라진다.

호출 시 리뷰 범위를 그대로 넘긴다. `REVIEW_SCOPE` 가 비어 있으면 인자 없이
호출해 원본의 기본 동작(현재 브랜치 변경분)을 그대로 쓴다.

## Degraded Behavior

위임 대상이 없으면 **결과를 지어내지 말고** 렌즈 상태를 그대로 보고한다.

- `~/.agent-crew/commands/review.md` 가 없으면 → `degraded`,
  이유 `delegation_target_missing`.
- 원본이 빈 리포트나 형식 이탈 결과를 내면 → 재시도하지 말고 `degraded`,
  이유 `delegate_output_unusable`. 원본 출력을 그대로 첨부한다.
- 변경 파일이 0건이라 원본이 조기 종료하면 → `not-run`,
  이유 `no_changes_in_scope`. 이것은 실패가 아니다.

어느 경우에도 `completed` 로 올리지 않는다.

## Read-Only Contract

이 렌즈는 읽기 전용이다. 원본도 read-only 서브에이전트를 쓰지만, 래퍼 쪽에서도
다음을 금지한다: 코드 수정, `git add`/`commit`/`push`, MR 노트 작성이나
description 갱신, 배포. 원본이 말미에 제안하는 `/fix`, `/mr`, `/analyze` 같은
다음 액션은 **제안으로만 옮기고 실행하지 않는다.**

## Artifact

결과를 `TASK_DIR/context/review-synthesis/generic-review.md` 에 쓴다.
원본의 출력 구조(`Risk Level`, `Files Reviewed`, `Must Fix`, `Should Fix`,
`Suggestions`, `Good Practices`)를 **손대지 않고 그대로** 보존한다. 요약하거나
재작성하지 않는다 — 종합 단계에서 축약한다.

## Synthesis Mapping

`review-synthesis` 가 이 렌즈 결과를 종합할 때:

- `Must Fix` → `반드시 봐야 할 문제`
- `Should Fix` → `주의할 항목`
- `Suggestions` → `주의할 항목`. 분량이 넘치면 `그 외 N건` 으로 접고 아티팩트
  경로를 가리킨다.
- `Good Practices` → 종합 보고서에 올리지 않는다. 아티팩트에만 남긴다.
- `Risk Level` 은 렌즈 단위 신호로 유지하고, 다른 렌즈의 심각도와 합산하거나
  평균 내지 않는다.

모든 항목에 `source_lens=generic-review` 라벨을 붙인다. 실제 위임 명령 경로는
아티팩트에 기록하되, 사용자 보고서에서는 렌즈 ID 로 표기한다.

`candidate_disposition` 은 이 렌즈가 정하지 않는다. 리뷰 결과는 후보 입력이므로
`Unknown` 으로 넘기고, 판정은 `review-synthesis` 의 Feedback Triage Boundary 가
수행한다.

## Caller Graph Coverage

원본은 로컬 diff 기반이고 호출 그래프를 추적하지 않는다. 따라서 이 렌즈의
caller graph coverage 는 항상 `not_applicable` 로 보고한다. 이 값을 근거로
더 강한 완료 주장을 만들지 않는다.

## Skip

- 원격 MR 반영률이 필요하면 `mr-review-rate` 렌즈를 쓴다. 이 렌즈는 로컬 전용이다.
- 구현 후 하드닝 점검은 `post-audit` 렌즈가 맡는다.
- 계약 정합성 비교는 `parity-check` 렌즈가 맡는다.
