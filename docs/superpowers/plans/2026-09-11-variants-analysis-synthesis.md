# Variants 구현 분석·종합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 또는 superpowers:executing-plans를 사용하여 승인된 실행 방식으로 단계별 구현한다. 이 문서는 계획이며 구현·설치·커밋 승인이 아니다.

**Goal:** 같은 요구사항을 구현한 후보들의 코드 자체를 육하원칙으로 분석하고, 기능별 장단점과 채택 근거를 비교하여 검증된 장점을 결합한 최종 구현을 제공한다.

**Architecture:** 기존 독립 후보 worktree, 완료 대기, 해시/토큰 기반 재개, 원본 반영 승인 경계는 유지한다. 후보 분석과 비교 판단은 호스트 AI가 수행하고, native CLI는 증거 정합성·상태 전이·중복 실행 방지만 담당한다. 후보 선택에서 끝나던 기본 흐름을 분석 -> 비교 -> 종합 구현 -> 독립 검증 -> 최종 산출물 제시로 바꾼다.

**Tech Stack:** 기존 Python CLI/runtime, Bash CLI adapter, JSON Schema, Markdown, Git worktree, pytest, shell/integration harness. 신규 외부 의존성은 기본적으로 추가하지 않는다.

**Spec:** 이 문서의 `요구사항 정본`, `분석 계약`, `종합 계약`, `상태와 승인` 절.

## 요구사항 정본

사용자 원문을 수정하지 않고 보존한다.

> 비교리뷰를 안해주는거같음 육하원칙으로 구현을 리뷰하고 장단점 비교해서 서로의 장점을 합하고 베스트프래틱스를 채택해서 높은 품질의 결과물을 얻고자 하는것이 목적임

> 선택하는것도 육하원칙이지만 구현을 분석하는것도 그러라는거임ㅁ

> 다시 어떻게 개선해야할지 분석하고 계획세워

계획 작성 당시 요청은 분석·계획이었다. 이후 사용자의 "순서대로 모두 완료할때까지 끊지말고 진행"에 따라 아래 구현과 로컬 검증을 진행한다. 육하원칙은 후보 전체에 붙이는 여섯 개 제목이 아니라 주요 구현 단위의 동작과 설계를 설명하는 기준이다. 후보 선택/채택 근거에도 별도로 적용한다.

## Global Constraints

- 작업 대상은 `/Users/wook/Developments/agent-crew`의 variants 흐름이다. 관련 없는 review-lens 변경은 건드리지 않는다.
- 후보 원문, 원본 기준 SHA, 후보별 SHA, 승인된 범위와 실행 그래프를 고정한다.
- native CLI, status, hook, resume 자체가 숨겨진 AI 실행을 시작하지 않는다. 승인된 호스트 orchestrator가 상태에 따라 에이전트를 위임한다.
- 분석/비교는 읽기 전용이다. 종합은 별도 worktree에서 수행하며 원본과 후보들을 수정하지 않는다.
- 전체 후보 브랜치 merge, 자동 원본 checkout/reset, 원격 push/MR/deploy는 제외한다.
- 구조 검사 통과는 리뷰 품질이나 실행 사실의 증명이 아니다. 내용 판정과 최종 품질 검증은 독립 reviewer 책임이다.
- 검증용 산출물은 실제 코드 분석과 실행 결과를 담는다. 형식만 맞춘 증명 파일이나 육하원칙 제목만으로 완료 처리하지 않는다.
- 후보 중 하나만 유지하는 편이 더 낫다면 허용한다. 억지로 여러 후보의 코드를 섞지 않는다.
- 기존 일반 parallel/run/agent와 일반 reviewer 모드는 바꾸지 않는다.

## 구현 전 진단

2026-09-11 계획 작성 당시 로컬 소스 확인 기준이다. 아래 경로와 라인은 구현 전 스냅샷이다.

| 근거 | 현재 동작 | 목적과의 차이 |
|---|---|---|
| `core/commands/run.md:1606-1618` | 리뷰 완료 후 기존 보고서를 재사용하고 사용자 선택을 기다린다. | 종합 구현과 최종 검증 단계가 없다. |
| `core/scripts/crew-runtime.py:2839` | NEXT가 collect 후 하나를 선택하라고 안내한다. | 호스트 안내도 후보 선발을 최종 목표로 유도한다. |
| `core/scripts/variant-session-collect.py:325-340` | 완료 보고서 해시가 같으면 `review_complete`를 반환한다. | 분석 범위·내용·비교·채택안 충족 여부는 알 수 없다. |
| `core/scripts/variant-session-collect.py:343-388` | token, input hash, 비어 있지 않은 report를 확인한다. | 한 단어 보고서도 구조상 완료 등록이 가능하다. |
| `tests/python/test_variant_resume.py:151` | `report.write_text("review")`를 정상 완료 테스트에 사용한다. | 지금 테스트는 수명주기를 검증하지, 비교 리뷰 품질을 검증하지 않는다. |
| `core/scripts/variant-session-collect.py:283-312` | 파일 해시를 모으고 base를 원본의 현재 HEAD에서 읽는다. | 공통 요구사항 목록·처리 흐름·고정 비교 기준이 없다. `pre_run_head`를 비교 기준으로 사용해야 한다. |
| `core/schemas/session.schema.json` | 후보·선택·apply 필드는 있지만 최종 종합 산출물 계약은 없다. | 비교 완료와 작업 전체 완료를 구분할 모델이 부족하다. |

이전 실제 리뷰 보고서도 기능 구현을 후보당 한 행으로 요약하고 기존 unittest 통과 및 스타일 차이를 근거로 하나를 추천했다. 이는 일부 코드 검토는 수행했다는 증거지만, 요청한 단위별 육하원칙 분석과 장점 종합을 수행했다는 증거는 아니다.

## 분석 계약

### 분석 단위와 범위

1. 변경 전 공통 요구사항에 안정적인 `requirement_id`를 부여한다. 원문은 별도 필드로 그대로 둔다.
2. 각 요구사항의 진입점에서 호출 관계를 따라 입력 -> 검증 -> 핵심 처리 -> 저장/외부 호출 -> 반환 -> 예외 경로를 추적한다.
3. 공통 `unit_id`는 후보별 파일명이 아니라 동작/책임 단위를 식별한다. 후보마다 구조가 달라도 같은 책임끼리 비교한다.
4. 주요 변경 hunk를 단위에 매핑한다. 변경되지 않았지만 계약에 영향을 주는 호출자/피호출자도 근거로 포함한다.
5. 분석하지 않은 영역, 누락 요구사항, 후보 고유의 추가 구현을 따로 표시한다. 모든 함수에 중복 문서를 붙이지 않는다.

### 각 후보 × 각 주요 구현 단위의 육하원칙

| 관점 | 반드시 설명할 내용 |
|---|---|
| 누가 / who | 호출 주체, 처리 책임 객체, 상태 소유자. 작성 AI의 이름만 적는 것은 부적합. |
| 언제 / when | 호출 조건, 실행 순서, 트랜잭션/비동기 시점, 재시도·동시성·실패 시점. |
| 어디서 / where | 파일/심볼/계층, 프로세스·저장소·외부 시스템 경계, 의존 방향. |
| 무엇을 / what | 입력·출력, 상태 변화·부작용, 요구사항 충족/누락, 불변조건. |
| 어떻게 / how | 알고리즘, 데이터·제어 흐름, 검증·예외·자원 관리 방식, 복잡도와 제한. |
| 왜 / why | 계약과 기존 설계에 비춘 적합성, trade-off, 대안 대비 이유. 작성 의도는 근거가 없으면 추정으로 표시. |

각 항목은 `statement`, `basis: observed|inferred|unknown|not_applicable`, `evidence[]`, `reason`을 가진다. `observed`에는 고정 SHA의 파일/심볼/라인 또는 실제 실행 로그를 연결한다. `inferred`에는 추론 근거와 한계를, `unknown`에는 부족한 정보를, `not_applicable`에는 적용되지 않는 이유를 적는다. 필수 정확성/보안 계약의 unknown은 종합으로 넘기지 않고 차단한다.

예: 중복 요청 처리는 `누가=consumer/service`, `언제=재전달·동시 요청`, `어디서=트랜잭션/DB 경계`, `무엇을=중복 부작용 방지`, `어떻게=키/제약/상태 검사`, `왜=재시도 계약 충족`으로 분석한다. 후보 선택 이유를 이 자리에 대신 쓰지 않는다.

### 공통 비교와 Best Practice

- 같은 단위에서 후보별 정확성, 실패·복구, 보안, 동시성, 성능 비용, 복잡도, 테스트 가능성, 호환성을 비교한다. 해당 없는 축에는 이유를 적는다.
- 장점·단점마다 근거와 영향, 재사용 가능한 요소, 결합 시 충돌을 기록한다.
- 정확성·보안·계약의 실패는 스타일 점수로 상쇄하지 않는다. 단일 합산 점수를 선택 근거로 삼지 않는다.
- 관행 채택은 저장소 규칙/기존 패턴과 요구사항을 우선한다. 추가 외부 근거가 필요하면 해당 버전의 공식 문서를 확인하고 출처를 남긴다.
- 개인적인 스타일 선호를 보편적 모범 사례로 표기하지 않는다. 최선이라는 표현은 실제 검증 범위로 제한한다.
- 후보 자체 테스트와 별개로 동일한 공통 acceptance 사례를 후보 전체와 최종 구현에 실행한다. 관찰하지 않은 성능 개선은 주장하지 않는다.

## 종합 계약

- 비교 reviewer가 단위마다 `adopt`, `adapt`, `reject`, `retain`과 원 후보/SHA/심볼, 장단점, 대안, 조합 제약, 검증 방법을 기록한다.
- 이 채택 결정에도 육하원칙을 적용한다. 결정 주체/책임, 적용 조건/시점, 적용 위치, 채택할 요소, 변환 방법, 대안 대비 이유를 구분한다.
- 결과는 기능·계약·오류 의미·자료 구조·의존 관계가 일관된 하나의 종합 구현안이어야 한다. 서로 양립하지 않는 장점은 병렬로 채택하지 않는다.
- 종합 worktree는 고정 `pre_run_head`에서 생성한다. 구현자는 승인된 구성 요소를 옮기거나 재구현하며 후보 전체 merge를 하지 않는다.
- 단일 후보를 최종 기반으로 유지하는 경우에도 별도 최종 산출물, 유지 이유, 공통 검증 및 독립 리뷰는 제공한다. 불필요한 코드 변경을 만들지는 않는다.
- 각 채택 결정은 `decision_id -> 최종 diff/심볼 -> 검증 사례`로 추적한다. 구현 중 계획 변경은 새 해시/재검토로 처리한다.
- 최종 reviewer는 종합 구현자와 분리한다. 요구사항, 채택안 이행, 조합으로 생긴 회귀, 보안/실패 경계를 검증한다.
- 최종 품질은 주장으로 보장하지 않는다. 비교표, 실행 로그, 해결된 결함/남은 제한으로 개선 효과를 입증한다.

## 산출물과 책임

| 산출물 | 책임과 내용 |
|---|---|
| `variant-review.json` | 구조화 정본. 원문·기준 SHA·요구사항/단위 목록·후보별 육하원칙·비교·채택안·근거 참조·검토 판정. |
| `variant-review.md` | 위 정본에서 렌더링한 사용자용 분석/비교/종합안. 내용 없는 점수표로 대체하지 않는다. |
| `variant-synthesis-state.json` | 입력 해시, 단계/시도 토큰, 실행 ID, 독립 worktree/branch, 최종 SHA, 검증 결과와 복구 이력. |
| 종합 task의 기존 결과/검증 산출물 | 기존 supervisor/TDD/quality-loop 형식을 사용한다. 별도의 중복 증명 파일 체계를 만들지 않는다. |

초기안은 후보별 기존 reviewer가 `MODE: variant-analysis`로 단위별 분석을 남기고, 별도 비교 reviewer가 교차검증·조합안을 작성하는 방식이다. 기존 reviewer 분석을 활용해 N개의 추가 분석 에이전트를 무조건 생성하지 않는다. 생성자 자기 설명은 참고 자료이며 독립 분석을 대신하지 못한다.

## 상태와 승인

새 세션에 `variants_workflow_version: 2`와 `outcome_mode: synthesis`를 기록한다. 사용자 기본 경험은 추가 명령 없이 아래 단계를 이어간다.

```text
implementing -> analysis_required -> comparing
             -> synthesis_required -> synthesizing
             -> validating -> ready_for_apply
```

각 단계는 `running`, `blocked`, `failed`, `stale` 및 재시도 receipt를 가진다. 내부 `next_action`으로만 위임을 안내하며 CLI가 AI를 실행하지 않는다. 후보 전부 종료는 collection 완료일 뿐, v2 session 전체 완료가 아니다.

- 최초 실행 승인 범위에 후보 구현 + 분석/비교 + 로컬 종합 + 최종 검증 그래프/비용 상한을 포함한다. 승인 범위 안의 단계 이동은 반복해서 사용자에게 묻지 않는다.
- 범위 밖 새 요구사항, 외부 부작용, 예산 초과, 고위험 변경은 재승인한다. 원본 apply는 기존 plan hash 승인으로 별도 유지한다.
- v1 세션은 읽기/재개/기존 apply를 유지한다. 과거 추천 보고서를 v2 분석 완료로 승격하지 않는다. v2 승격은 추가 실행 그래프 승인 후 새 분석으로 시작한다.
- 입력 해시는 workflow/계약/리뷰 정책 버전, 원문 요구사항, 고정 base SHA, 후보 SHA와 의미 있는 검증 증거를 포함한다. 단순 진행 로그 갱신과 실제 입력 변경을 분리한다.
- 입력 변경은 영향받은 단계와 후속 결과를 stale로 만든다. 완료 리뷰/종합 구현의 재사용은 해당 해시가 일치할 때만 허용한다.
- 실행 토큰과 호스트 실행 ID를 함께 기록한다. 중단 후 기존 실행이 살아 있으면 재위임하지 않는다. 종료 확인 후 명시적으로 해제하고 새 시도 토큰을 발급한다.
- 전체 실패는 blocked, 한 후보만 유효하면 비교 제한을 명시, 동일 SHA는 동등 후보로 표시한다. 실패 후보의 코드는 검증 없이 채택하지 않는다.
- 종합 결과는 `tasks` 후보 목록에 끼워 넣지 않는다. collection barrier가 종합 task까지 기다리는 순환을 방지한다.
- 원본 반영 경로는 legacy candidate 또는 v2 final artifact를 명시적으로 구분한다. `selected_task_id`를 몰래 바꿔 기존 apply 검증을 우회하지 않는다.

## 구현 순서

아래 경로는 저장소 루트 기준이다. 각 단계는 실패 테스트 -> 최소 구현 -> 통과 -> 범위 리뷰 순서로 진행한다. 커밋/설치는 별도 승인된 경우에만 수행한다.

체크는 해당 목적의 구현과 검증 완료를 뜻한다. 아래 설명용 테스트 이름은 최초 설계명이며 실제 테스트는 `tests/python/test_variant_*.py`에 있다. fixture의 구체적 도메인 조정과 실제 실행 한계는 실행 검증 기록을 따른다.

### Task 1: 분석·비교 계약과 부족한 보고서 거부

**Files:** Create `core/schemas/variant-review.schema.json`, `core/scripts/variant_review.py`, `tests/python/test_variant_review_contract.py`; Modify `core/scripts/variant-session-collect.py`, `tests/python/test_variant_resume.py`, `core/commands/variants.md`.

**Interfaces:** `validate_review(document: dict, inputs: dict) -> list[str]`, `render_review(document: dict) -> str`. 문서 최상위는 `schema_version`, `input_hash`, `requirements`, `units`, `candidate_analyses`, `comparison`, `decisions`, `semantic_review`로 고정한다. 조건 검증은 구조·식별자·근거 정합성에 한정한다.

- [x] `v2_report_requires_analysis_per_candidate_unit`, `missing_why_rejected`, `unknown_requires_reason`, `decision_requires_source_and_validation`, `single_word_report_rejected` 실패 테스트를 작성한다.
- [x] `python3 -m pytest tests/python/test_variant_review_contract.py -q`에서 의도한 실패를 확인한다.
- [x] JSON Schema 및 교차 참조 검사, Markdown 렌더링을 구현한다. v2의 `review --complete --report PATH`는 JSON 정본을 받고 MD를 렌더링한다. v1 Markdown 경로는 명시적 legacy 처리로 유지한다.
- [x] 스키마 통과와 semantic review 승인 여부를 분리한다. `semantic_review`의 실패/미확인 상태를 완료로 취급하지 않는다. 실행 ID 없는 자체 승인 문구는 신뢰하지 않는다.
- [x] `tests/python/test_variant_resume.py`를 v1 유지/v2 강화로 분리하고 재실행한다.

대표 계약 테스트 설계:

```python
def test_missing_why_rejected(valid_review, review_inputs):
    # 주요 구현 단위의 분석 누락은 제목이나 추천 문구로 보충할 수 없다.
    del valid_review["candidate_analyses"][0]["units"][0]["five_w_one_h"]["why"]
    errors = validate_review(valid_review, review_inputs)
    assert any("why" in error for error in errors)
```

### Task 2: 공통 입력·분석 범위·기준 커밋 고정

**Files:** Modify `core/scripts/crew-runtime.py`, `core/scripts/variant-session-collect.py`, `core/schemas/session.schema.json`; Create `tests/python/test_variant_review_inputs.py`.

**Interfaces:** 기존 `review_inputs(session)` 반환값을 versioned 계약으로 확장한다. `base_commit=session.pre_run_head`, 후보별 commit, 원문 요구사항 참조, `requirement_id/unit_id`, 증거 manifest를 제공한다. 기존 계약과 구분하는 version을 반드시 포함한다.

- [x] `base_head_movement_does_not_change_comparison_base`, `missing_base_requires_explicit_legacy_resolution`, `changed_candidate_invalidates_review`, `progress_log_does_not_invalidate_review`, `changed_acceptance_evidence_invalidates_review` 테스트를 작성하고 실패를 확인한다.
- [x] 비교 기준 SHA를 최초 실행부터 모든 worktree 생성·diff·검증에서 일관되게 사용한다. 현재 HEAD를 읽어 조용히 대체하지 않는다.
- [x] AI가 작성한 요구사항/단위 목록은 실제 원문과 코드의 근거 참조를 검증한다. deterministic helper가 LLM 분석을 한 것으로 표시하지 않는다.
- [x] 대상 저장소가 Git이 아니거나 고정 기준을 입증할 수 없으면 자동 종합을 차단하고 이유를 반환한다.
- [x] 해당 테스트와 기존 `test_variant_collect_wait.py`, `test_variant_resume.py`, `test_variant_apply.py`를 실행한다.

### Task 3: 호스트 분석·교차 비교 연결

**Files:** Modify `core/commands/run.md`, `core/commands/variants.md`, `core/agents/reviewer.md`; Create `core/agents/skills/variant-analysis.md`, `tests/python/test_variant_orchestration_contract.py`.

**Interfaces:** `MODE: variant-analysis`는 후보별 구현 분석을 반환한다. `MODE: variant-comparison`은 같은 단위의 분석을 교차 확인하고 비교/decisions를 반환한다. 일반 reviewer 모드는 변경하지 않는다.

- [x] `analysis_mode_requires_runtime_responsibility_not_author_name`, `comparison_requires_common_units`, `review_completion_does_not_stop_at_selection`, `normal_reviewer_unchanged` 계약 테스트를 먼저 추가한다.
- [x] 스킬에 육하원칙의 코드 분석 의미와 observed/inferred/unknown/N/A 규칙을 명시하고 각 호출에서 정확한 스킬을 로드한다.
- [x] reviewer에 diff만 주지 않고 영향 경로·요구사항·공통 테스트·실제 파일 접근을 제공한다. 선호 패턴은 적용 이유와 비용을 함께 설명하게 한다.
- [x] 런타임 NEXT, P4, injection, resume 안내를 함께 점검한다. v2 분석 시작 이후 후보 추가는 기존 실행에 조용히 섞지 말고 새 승인 revision으로 처리한다.
- [x] 구조 검사 통과지만 의미가 부실한 fixture도 reviewer가 거절하는 실제 호스트 검증을 Task 6에 연결한다. 문자열 검사만으로 이 요구사항을 완료 처리하지 않는다.

### Task 4: 종합 실행과 재개

**Files:** Create `core/scripts/variant_synthesis.py`, `core/schemas/variant-synthesis-state.schema.json`, `tests/python/test_variant_synthesis.py`; Modify `core/bin/crew`, `core/scripts/variant-session-collect.py`, `core/scripts/crew-runtime.py`, `core/commands/variants.md`, `core/commands/run.md`.

**Interfaces:** 최초 설계는 `prepare_synthesis`와 `record_synthesis_result`를 제안했다. 실제 구현은 두 함수에 고정 `inputs`를 명시적으로 전달한다. native CLI의 `crew variants synthesize --prepare INPUT_HASH`, `--complete TOKEN --result PATH`, `--release TOKEN` 및 실제 host ID bind가 구현되어 있다.

- [x] `review_complete_routes_to_synthesis`, `synthesis_uses_independent_worktree_at_pinned_base`, `original_and_candidates_unchanged`, `resume_does_not_duplicate_synthesizer`, `old_token_rejected`, `incompatible_decisions_blocked`를 먼저 실패시킨다.
- [x] 기존 Git worktree helper를 필요한 만큼만 확장하고 고정 기준 SHA를 인자로 받게 한다. source runtime 우회로 공유 checkout을 만드는 fallback은 금지한다.
- [x] 기존 supervisor와 TDD/quality-loop를 종합 task에 재사용한다. candidate 목록과 final artifact는 별개로 저장한다.
- [x] 분석/정책 버전 변경 시 기존 결정과 종합 결과를 stale로 만들고 새 검토를 요구한다. 토큰 해제는 호스트 종료 확인 후에만 한다.
- [x] 범위 내 자동 수정은 최초 승인한 retry/cost budget 안에서만 반복하고, 초과는 blocked로 보고한다.

대표 재개 테스트 설계:

```python
def test_synthesis_is_not_a_new_candidate(synthesis_ready_state):
    # 종합 task를 후보 barrier에 넣으면 실행 순환과 개수 변조가 생긴다.
    before = read_session(synthesis_ready_state)["candidate_count"]
    prepared = prepare_synthesis(synthesis_ready_state, approved_hash(synthesis_ready_state))
    assert read_session(synthesis_ready_state)["candidate_count"] == before
    assert prepared["artifact_kind"] == "synthesis"
```

이 테스트의 `read_session`은 session.json을 읽는 테스트 helper, `approved_hash`는 fixture의 승인된 review.input_hash를 반환하는 helper로 해당 테스트 파일 안에 정의한다.

### Task 5: 최종 품질 게이트와 명시적 반영 연결

**Files:** Modify `core/scripts/variant_synthesis.py`, `core/scripts/variant-session-collect.py`, `core/commands/variants.md`; Create `tests/python/test_variant_final_validation.py`; Extend `tests/python/test_variant_apply.py`.

**Interfaces:** 최종 `validation`은 common acceptance 결과, 종합 SHA, 독립 reviewer의 실행 ID/verdict, unresolved findings, 결정별 이행 결과를 기록한다. `ready_for_apply`는 이 검증 결과의 최신성이 확인된 경우에만 반환한다. 제안하는 `apply --artifact final --target BRANCH --dry-run|--confirm HASH`는 legacy 후보 apply와 입력을 명시적으로 구분한다.

- [x] `accepted_features_all_present`, `new_composition_regression_blocks_ready`, `reviewer_is_not_synthesizer`, `failed_checks_not_overridden_by_style`, `stale_final_sha_rejected`, `final_apply_never_changes_selected_task_id` 테스트를 작성하고 실패를 확인한다.
- [x] 요구사항 공통 테스트 + 채택 요소별 테스트 + 조합 경계 회귀 테스트를 실행한다. 후보 테스트를 전부 복사하기보다 공통 검증 계약에 맞춰 통합한다.
- [x] 최종 reviewer가 종합 코드의 주요 단위를 육하원칙으로 확인하고 비교/채택안과 구현이 일치하는지 판정한다.
- [x] 오류는 기존 quality-loop를 재사용하여 종합 구현자로 되돌린다. 테스트를 줄이거나 요구사항을 약화해서 통과시키지 않는다.
- [x] ready_for_apply에서 사용자에게 분석/비교, 채택·기각 이유, 최종 diff/SHA, 검증 결과와 남은 한계를 제공한다. 원본 반영은 별도 승인으로 유지한다.

### Task 6: 목적 중심 통합 검증

**Files:** Create `tests/integration/test_variants_synthesis.bash`, `tests/python/test_variant_synthesis_e2e.py`; Update 관련 CLI contract tests의 variants 부분만.

- [x] 결정론적 fixture는 공백 정규화/순서 보존 중복 제거의 서로 다른 두 강점을 사용하고, 실제 AI fixture는 같은 CSV 계약을 독립 구현한 세 후보의 구조/경계 테스트 강점을 비교한다. 자원 해제는 도메인에 맞게 호출자 소유 자원을 닫지 않는 계약으로 검증한다.
- [x] 공통 acceptance에는 A/B/C 중 하나를 그대로 고르면 놓치는 요구사항과 결합 시 충돌하는 계약 사례를 포함한다. 최종 결과가 전부 충족하는지 확인한다.
- [x] 별도 fixture에서는 한 후보가 이미 최선인 경우, 전부 실패, 후보 한 개만 유효, 동일 SHA, 증거 부족, 의미 없는 육하원칙 보고서, 중단 후 재개를 검증한다.
- [x] 로컬 deterministic 검증: `python3 -m pytest tests/python/test_variant_*.py -q`, `bash tests/integration/test_variants_synthesis.bash`, `bash tests/shell/test_crew_cli.bash`, `git diff --check`.
- [x] 전역 설치 승인을 받은 뒤 drift 검사와 새 임시 저장소의 실제 `crew:run --variants 3`을 실행한다. 후보 구현/단위별 분석/교차 비교/종합 구현/독립 최종 리뷰까지 추가 사용자 요청 없이 이어져야 한다.
- [x] 실제 AI 실행은 fixture receipt로 대신하지 않는다. 구조 통과 여부뿐 아니라 육하원칙이 구현 동작을 설명하는지, 장단점이 실제 채택안과 최종 코드로 이어졌는지 사람이 읽을 수 있는 결과로 확인한다.
- [x] 원본·후보 SHA/작업 파일, 최종 산출물 별도 존재, 선택·merge·push 미실행, 승인 범위 보존을 전후 비교한다.

## 완료 기준

### 실행 검증 기록

- Task 1~6 구현, 독립 코드 리뷰, 로컬 설치, 결정론적 회귀 및 실제 호스트 E2E를 완료했다. 의미 검증은 실제 reviewer의 코드 분석·테스트·판정을 근거로 하며 JSON 필드 존재로 대신하지 않았다.
- handoff 계획 분기, parent child bridge, 복구된 후보 blocker 정리, 종합 supervisor MODE 생성/계획 재작성 보존을 포함한 variants/상태 스키마/supervisor/quality-plan 최종 회귀: 287 passed (`/private/tmp/crew-v2-host-I74JvM/final-regression.log`).
- analyst의 handoff 재작성 과정에서 모드 표기가 누락된 실제 사례를 동일 analyst가 수정했다. analyst 및 pipeline-planning 지침에 종합 실행일 때만 두 표기를 보존하도록 보강했다. 독립 리뷰의 정적 검사 부족 finding은 handoff 절의 조건부 적용/잘못된 모드 금지/일반 계획 제외를 각각 검증하여 resolved로 확인했다. 정적 검사 자체는 AI 의미 품질 보장이 아니다.
- CLI 전체 회귀: 164 tests / 476 assertions passed. 세션별 산출물 경로를 사용하는 native 통합 테스트도 통과했다.
- 독립 리뷰에서 발견한 세션 덮어쓰기 경쟁과 stale 해시 덮어쓰기 결함을 수정했다. 재현 포함 8개 검증으로 두 finding resolved를 확인했다.
- 기존 사용자 review-lens 변경을 보존하여 전역 설치했고 install drift 검사가 통과했다. mnemos 규칙 갱신, 소스 커밋 및 원격 작업은 하지 않았다.
- 실제 호스트 E2E 작업 경로: `/private/tmp/crew-v2-host-I74JvM`. 첫 20260911-005024 세션은 placeholder를 승인된 resume으로 오인하여 계획 단계를 생략했으므로 전부 blocked로 보존했다. 정상 성공으로 집계하지 않는다.
- `planning_required`와 읽기 전용 `supervisor-start-mode.py`, quality-plan의 `unplanned_handoff` 차단으로 위 결함을 수정했다. 독립 리뷰 46개 검증에서 추가 finding이 없었다.
- 수정 설치본의 새 20260911-011548 세션에서 독립 후보 셋과 각 후보의 5개 동작 단위별 육하원칙 분석을 완료했다. 별도 비교 reviewer가 고정 후보마다 공통 및 후보 경계 테스트 59개를 실행하여 총 177회 통과를 확인했다. 이는 중복 포함 실행 수이며 서로 다른 계약 177개라는 뜻이 아니다.
- 실제 비교 리뷰는 structural 서비스 구조와 기존 테스트를 유지하면서 minimal/balanced의 네 경계 테스트 강점을 보강하는 9개 결정을 등록했다. `synthesis_required` 이후 별도 최종 worktree에서 analyst, checklist, 독립 checklist review, test-writer RED, backend GREEN/Refactor, commit 후 검증, 독립 final review까지 완료했다.
- 별도 synthetic 부정 fixture는 실제 SHA/라인과 JSON 구조 검사를 통과했지만, 독립 reviewer가 일반론 반복·무관한 근거·구체적인 비교/결합 부재로 `needs_changes` 판정했다. 이 fixture는 실제 완료/승인으로 등록하지 않았다.
- requirements 역할의 계정 미지원 gpt-5.4 실행은 성공으로 세지 않았다. 설정을 변경하지 않고 동일 installed 역할 정의를 현재 호스트 기본 모델로 실행하여 요구사항을 확보했다.
- 중첩 worker에는 child 도구가 없어 부모 호스트가 supervisor의 요청/실제 응답만 중계한다. 세 후보 모두 실제 analyst의 계획과 installed quality/capability 검사 PASS를 확보했다. Markdown 경로가 완료 프로토콜을 통과하지 못한 두 응답은 실제 analyst 역할이 평문 경로로 다시 반환했다.
- 실제 TDD/리뷰 기록은 각 task의 child-request 및 child-dispatch 파일에 실제 host ID로 연결했다. 중계자가 계획/구현/리뷰 결과를 대필하지 않았다. 최종 supervisor와 backend, reviewer의 실제 ID는 서로 다르다.
- 최종 commit은 `15b7e0c818a0279e1bde00253c8d625facb30d40`, branch는 `codex/variants-20260911-011548-final-1`이다. 요구사항 5개, 결정 9개, 구현 단위 5개의 육하원칙 및 조합 검사 4개를 실제 최종 코드/로그와 연결했다. 고유 테스트는 공통 7개 + 추가 22개 = 29개이며 조합 4개는 추가 22개의 부분집합이다.
- 독립 final reviewer는 APPROVED, unresolved none을 반환했다. test-writer의 mapping 표기와 reviewer 응답의 QUALITY_METRICS 경로 누락은 동일 원작성자가 실제 근거를 보존하여 보완했다. 코드/테스트를 약화하거나 reviewer 판정을 대필하지 않았다.
- native `synthesize --complete`는 실행 1회/등록 검증 1회에 `ready_for_apply`를 반환했고 반복 resume도 같은 task/token/worktree/commit을 유지했다. 원본 `main`은 최초 `5b84ad1dfb2ae391c664fb3d6d00d9501fe99855` 그대로이며 candidate 선택은 pending/null, 원본 apply/merge/push는 하지 않았다.
- 최종 apply 미리보기의 legacy 후보 표기와 누락된 `--artifact final` 확인 안내를 수정했다. 독립 리뷰 finding 없음, 적용 회귀 33개 및 별도 출력 검사 3개가 통과했다. 미리보기만 실행했고 confirm은 실행하지 않았다.
- runtime quality gate는 실제 증거를 기반으로 통과했다. phase-note 탐색과 독립 span 연결의 advisory는 남겨 두었으며 실제 별도 host 실행/로그로 보완했다. capabilities.json, 수치 line/branch coverage, LSP/type checker는 미확보/미사용이다. 테스트 수나 workflow evidence score를 제품 품질/coverage 백분율로 오인하지 않는다.

### 실제 산출물

- 비교 정본/보고서: `/Users/wook/.agent-crew/state/project-23eaf7f82b/variants/20260911-011548/variant-review.json`, 같은 경로의 `variant-review.md`.
- 최종 독립 리뷰: `/Users/wook/.agent-crew/state/project-23eaf7f82b/variants/20260911-011548/synthesis/attempt-1/task/context/review.md`.
- 최종 구현 분석/결정 검증 정본: `/Users/wook/.agent-crew/state/project-23eaf7f82b/variants/20260911-011548/synthesis/attempt-1/task/synthesis-result.json`.
- 로컬 검증/격리 검사: `/private/tmp/crew-v2-host-I74JvM/final-regression.log`, `final-preview-regression.log`, `final-integrity.log`, `final-apply-preview.txt`.

### 최종 판정 항목

- 주요 구현 단위마다 후보별 육하원칙 분석과 고정 근거가 있다.
- 기능/계약 단위 장단점 비교와 호환성 검토가 있고, 채택·기각 결정이 설명된다.
- 채택 이유뿐 아니라 각 후보와 최종 코드의 동작 자체가 설명된다.
- 서로 다른 후보의 검증된 장점이 최종 코드에 반영되거나, 단일 후보 유지가 더 적합한 이유가 입증된다.
- 공통 acceptance와 조합 회귀 검사, 독립 최종 리뷰가 통과한다. 남은 불확실성은 숨기지 않는다.
- 초기 승인 범위 안에서 자동으로 최종 산출물까지 이어지고, 원본 반영은 별도 승인이다.
- 기존 v1 세션과 일반 parallel/run/agent가 깨지지 않고 기존 사용자 변경이 보존된다.

## 계획 자체 점검

- 사용자 요구 대응: 구현 분석은 Task 1~3, 장단점/채택 기준은 Task 1/3, 장점 종합은 Task 4, 최종 품질은 Task 5/6에 연결했다.
- 단순 제목/필드 검증이 의미 있는 리뷰를 보장하지 못한다는 한계를 별도 명시했다.
- 신규 실행은 종합까지 초기 승인하며 legacy 세션은 승인 없이 범위를 확대하지 않는다.
- 위 Task별 인터페이스 설명은 최초 계획 시점의 제안이며, 현재 구현/검증 현황은 실행 검증 기록을 기준으로 한다.
- Task 1의 보고서 계약과 실패 테스트부터 구현했으며 최종 판정은 실제 호스트 E2E와 함께 기록한다.
