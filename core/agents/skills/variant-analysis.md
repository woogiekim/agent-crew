# Variants 구현 분석 및 비교

## 적용 범위

`MODE: variant-analysis`, `MODE: variant-comparison` 또는 `MODE: final`과
`VARIANT_SYNTHESIS: true`가 명시된 경우에만 적용한다. 일반 reviewer의 기본 모드는
변경하지 않는다. 비교 reviewer는 read-only이며 지정된 리뷰 산출물만 작성한다.
이 스킬이나 native CLI가 AI 실행을 시작하지 않는다.

교차 비교 및 완료된 후보의 재분석 출력은 `session.variants_dir` 아래 호스트가 고정한 경로에 작성한다.
필드가 없는 기존 v1/구형 v2는 STATE_DIR를 사용한다. 신규 v2의 기준 경로는
STATE_DIR/variants/<session_id>이며 종합 task와 최종 검증 산출물도 이 아래에 둔다.
후보 task_dir 밖에 출력하며 후보 task 증거는 읽기만 한다.
후보 완료 전 기존 pipeline의 `MODE: variant-analysis` reviewer는 자기 task_dir에
자신의 지정 리뷰 산출물과 skill-load 기록을 작성할 수 있다. 기존 구현/테스트 증거를
수정하지 않으며, 이 리뷰 결과도 후보 완료 후 비교 입력 해시에 포함된다.
입력의 input_hash는
현재 해시이고 synthesis_input_hash는 기존 종합 receipt 해시이므로 혼동하지 않는다.

## 분석 절차

분석 대상은 **후보 × 행동 단위**의 구현 자체다. 후보 선택 이유만 여섯 제목으로
나열하지 않는다. 원문 요구사항을 보존하고 `requirement_id`를 부여한 뒤 각
진입점에서 입력 -> 검증 -> 핵심 처리 -> 저장/외부 호출 -> 반환 -> 예외 경로를
추적한다. 변경 hunk와 영향받는 호출자 및 피호출자를 공통 `unit_id`에 연결한다.
후보별 파일명이 달라도 같은 책임을 비교한다. 미분석 영역과 후보 고유 추가 범위는
명시하고 범위를 임의로 확대하지 않는다.

| 필드 | 구현 자체의 설명 |
|---|---|
| `who` | 호출 주체, 처리 책임 객체와 상태 소유자. 작성 AI 이름만 적지 않는다. |
| `when` | 호출 조건, 실행 순서, 트랜잭션, 비동기, 재시도, 실패 시점. |
| `where` | 파일/심볼/계층, 프로세스 및 저장소 경계와 의존 방향. |
| `what` | 입력/출력, 상태 변화, 부작용, 요구사항 충족과 불변조건. |
| `how` | 알고리즘, 제어/데이터 흐름, 오류 처리, 자원 관리와 복잡도. |
| `why` | 기존 계약과 설계의 적합성, 대안과 trade-off. 의도 추정은 표시한다. |

모든 항목은 `statement`, `basis`, `evidence` 배열, `reason`을 갖는다.
`observed`는 실제 고정 코드 또는 실행 로그, `inferred`는 근거와 추론 한계,
`unknown`은 부족한 정보와 실패 원인, `not_applicable`은 적용되지 않는 구체적
이유를 적는다. N/A는 누락 필드를 대신하지 않는다. 정확성/보안 등 핵심 계약의
해결되지 않은 unknown은 종합 채택을 차단한다. 비어 있는 일반론으로 채우지 않는다.

증거 객체는 두 형식으로 한정한다.

- 코드: `task_id`, `commit`, `path`, `line`. 고정 SHA에 실제 존재하는 상대 경로와 라인.
- 실행 산출물: `task_id`, `artifact`, `sha256`. task_dir 내부의 실제 파일과 고정 manifest 해시.

실제 파일/라인 및 로그를 열어 확인한다. 현재 HEAD나 dirty 파일로 고정 SHA를
대체하지 않는다. 실제 실행을 관찰하지 않은 성능/테스트 성공을 주장하지 않는다.

## JSON 정본

`core/schemas/variant-review.schema.json`과 `tests/fixtures/variants/review-v2.json`을
형식 기준으로 읽는다. fixture는 예제이며 placeholder SHA/ID/문장을 완료 증거로
복사하지 않는다. 최상위 필수 필드는 다음과 같다.

- `schema_version` = 2, `input_hash` = 현재 입력 해시.
- `base_task` = 수정하지 않은 원문, `base_commit` = 고정 pre_run_head.
- `requirements`: requirement_id, text. `units`: unit_id, requirement_ids, description.
- `candidate_analyses`: 후보별 task_id, commit, units. 각 공통 단위의 five_w_one_h와
  `strengths`/`weaknesses` 문자열 배열을 기록한다.
- `comparison`: unit_id, summary, compatibility, candidate_ids.
- `decisions`: decision_id, unit_id, action, `source_task_id`, `source_commit`,
  five_w_one_h, target, `validation`, compatibility.
- `semantic_review`: reviewer_id, verdict, unresolved_findings.

성공 후보는 모든 공통 단위의 완전한 구현 분석이 필요하다. 실패 후보는 성공으로
꾸미지 않고 단위별 실패/unknown 사유를 남긴다. 사용 가능한 고정 SHA가 없으면
commit을 추정하지 않는다. completed 후보의 분석 commit은 필수다. 실패 후보는
입력에 commit이 없으면 분석 commit을 생략하고 각 공통 단위의 육하원칙을
unknown과 구체적인 reason으로 진단한다. 실패 후보를 reject하는 결정도 고정 SHA가
없으면 source_commit을 생략할 수 있다. SHA가 제공된 경우에는 분석/결정과 일치해야 한다.
실패 후보는 무검증 채택하지 않는다. 전부 실패하면 blocked로 보고하며 approved
문서나 종합 구현을 만들어 완료를 가장하지 않는다.

## 비교 및 채택

같은 단위에서 정확성, 실패/복구, 보안, 동시성, 성능 비용, 복잡도, 테스트 가능성,
호환성을 비교한다. 해당 없는 비교 축은 이유를 적는다. 장점/단점은 고정 근거,
영향, 재사용 요소와 조합 충돌을 구체적으로 설명한다. 단일 점수나 스타일 선호로
정확성 실패를 상쇄하지 않는다. Best Practice는 저장소 규칙과 계약에 맞는 이유를
밝히고 관찰하지 않은 우월성을 단정하지 않는다.

모든 공통 단위에 비교와 decision을 남긴다. `adopt`/`adapt`/`reject`/`retain`
결정에도 별도의 육하원칙을 작성한다. 결정 주체, 적용 시점, 대상 위치, 채택 요소,
변환 방법, 대안 대비 이유를 구분한다. 원 후보/SHA, 검증 방법, 조합 제약을 연결한다.
한 후보 유지가 더 적합하면 허용하고 비교 한계와 유지 이유를 밝힌다.
동일 SHA 후보는 동등 후보로 표시하고 실패 후보의 코드는 채택하지 않는다.
서로 양립하지 않는 결정을 함께 승인하지 않는다.

## 독립 검증 및 한계

최종 reviewer는 실제 host ID가 종합 implementer ID와 달라야 한다. 공통 acceptance,
채택 요소, 조합 경계 회귀를 실제 실행하고 `decision_id` -> 최종 diff/심볼 ->
검증 사례를 추적한다. 최종 구현의 각 단위도 육하원칙으로 검토한다.
미해결 필수 finding은 `needs_changes`로 반환하고 기존 quality-loop로 수리한다.

최종 결과는 공통 acceptance뿐 아니라 채택 장점별 decision_results의
validation(passed, command, log), 비어 있지 않은 composition_checks의
name/passed/command/log를 요구한다. 모든 성공은 실제 실행 로그로 확인하고
synthesis task_dir 내부 로그의 SHA-256을 고정한다.

구조 검사는 의미 품질이나 독립 AI 실행 증명이 아니다. 실제 호스트 실행 이력,
실제 코드 분석, 실행 로그와 독립 reviewer 판단이 필요하다. 가짜 receipt, 임의
host ID, prompt-only 완료, 자기 설명을 독립 리뷰로 표시하는 행위를 금지한다.
내용이 빈약하면 JSON 검사를 통과했어도 승인하지 않는다.
