# Memory Provider Contract

agent-crew depends on the `core/bin/memory` wrapper as its stable memory
provider boundary. Runtime agents and hooks must call this wrapper instead of
calling mnemos internals or reading mnemos storage files directly.

## Commands

The provider surface is:

| Command | Required | Behavior |
|---|---:|---|
| `memory capture` | yes | Stores support memory when a backend is available. Adds `--no-classify` by default for agent-crew support captures. |
| `memory search` | yes | Executes the configured recall mode. Legacy mode returns best-effort text results; V2 mode preserves provider JSON. |
| `memory read` | yes | Reads one memory item by id. Defaults to the local support backend unless `MNEMOS_BACKEND` is set. |
| `memory gc` | yes | Delegates garbage collection to the configured Mnemos provider. |
| `memory convention` | yes | Manages local per-installed-user coding convention cache and task snapshots without requiring mnemos. |
| `memory closeout` | no | 명시적으로 확인한 교훈 한 건을 현재 프로젝트의 원본 근거와 함께 저장한다. |
| `memory feedback` | no | Forwards provider feedback JSON only when `AGENT_CREW_MEMORY_FEEDBACK=1`. |

## 검증한 교훈 마무리

작업에서 재사용할 교훈의 적용 조건, 판단, 현재 원본 근거를 확인한 뒤
다음 형식으로 프로젝트 안의 Markdown 파일 한 개에 기록한다.

```markdown
## 반납한 대여 ID 재시도

- Condition: 동일한 대여 ID를 같은 내용으로 다시 전송한다.
- Decision: 반납 상태와 기존 원장 기록을 유지한다.
- Evidence: gear_loan.py:41
```

`memory closeout docs/lesson.md --project-root . --verified`를 명시적으로
실행한다. `--verified`는 교훈이 현재 원본 및 검증 결과와 일치한다는
작업자의 확인이다. 도구는 프로젝트 안의 문서, 단일 섹션, 필수 필드와
원본 줄을 확인하고 공급자에 `project-context capture`를 요청한다.
출력의 `created`, `updated`, `skipped` 중 하나에서 기록 ID를 확인할 수
있다. 같은 문서·제목으로 다시 실행하면 기존 기록을 재사용한다.

다음 작업은 기본 Recall V2에서 동일한 프로젝트 ID와 루트 해시로 조회한다.
`memory.md`에는 교훈 문서의 경로와 섹션이 표시되고, 본문의 `Evidence`가
실제 근거 파일로 연결된다. `closeout`은 근거 경로·줄과 파일 전체의
지문을 저장한다. 해당 파일의 변경·삭제는 Agent Crew의 주입과 적용을
차단한다. 변경된 파일의 근거를 다시 검증하고 같은 교훈으로 `closeout`을
실행하면 ID가 유지되며 이전 근거에 대한 검토는 재사용되지 않는다.
이전에 저장된 지문 없는 교훈은 기존 검증 경로를 따른다.
동기화 동작은 선택한 공급자 설정을 따른다.

교훈 적용 검증과 피드백에는 현재 단계의 `--project-root`를 전달한다.
조회 당시의 정규화된 경로 및 프로젝트 컨텍스트 루트 해시를 대조한다.
체크아웃이 달라졌다면 그 위치에서 다시 조회하고 원본을 확인해야 한다.
적용 검증에 `--memory-bin`을 전달하면 교훈 ID의 최신 사용 가능 상태를 읽기
전용으로 확인한다. 폐기되었거나 상태를 읽을 수 없는 교훈은 적용 검증을
통과하지 않는다. 기존에 캡처한 조회 파일은 그대로 둔다.
검증할 교훈이 여러 건일 때는 공급자에 한 번 일괄 요청하고 ID별 응답을 확인한다.

## Recall Modes

`AGENT_CREW_MEMORY_RECALL_MODE` controls `memory search`. The default is `v2`:

| Mode | Behavior |
|---|---|
| `off` | Skips recall and exits `0` with `status=disabled` on stderr. |
| `legacy` | Opt-in compatibility mode that delegates to provider `mnemos search` and preserves the text result contract. It does not read provider storage directly. |
| `shadow` | Diagnostic mode that runs Recall V2 read-only, discards its output for planning, then returns the provider legacy text result. |
| `v2` | Calls `mnemos recall --json` and preserves stdout JSON. It does not read mnemos SQLite/FTS internals, truncate result bodies, synthesize scores, or fall back to state-changing legacy search when recall is unavailable. |

V2 컨텍스트 생성은 한 번의 조회에서 주입 한도의 4배까지 후보를 요청한다.
기본 balanced 설정은 후보 24개와 주입 최대 6개를 사용한다. Agent Crew는
후보의 상태·프로젝트 범위·관련성과 원본을 확인한 뒤 주입 건수 및 본문 크기
한도를 적용한다. 공급자의 전체 후보와 검증된 결과는
`memory-retrieval.json`에서 확인할 수 있다.

`AGENT_CREW_MEMORY_STRICT=1` makes wrapper-level provider incompatibility,
timeout, invalid JSON, and unavailable states fail non-zero. The default
`AGENT_CREW_MEMORY_STRICT=0` reports the state and lets workflows continue
without memory. `AGENT_CREW_MEMORY_FEEDBACK=1` enables `memory feedback`;
the default `0` keeps feedback disabled.

## Local User Convention Surface

`memory convention` is part of the provider boundary because agents need a
stable entry point, but it is not a remote repository data source. The command
stores actual convention content in the installed user's local cache under
`${AGENT_CREW_CONVENTION_CACHE_DIR:-${AGENT_CREW_HOME}/cache/user-conventions}`.
Different users can have different conventions for the same project checkout.

Supported subcommands:

| Subcommand | Behavior |
|---|---|
| `capture` | Adds a local convention for the owner. |
| `update <id>` | Updates an existing local convention and bumps the cache version. |
| `retire <id>` | Marks a convention retired so future snapshots exclude it. |
| `snapshot` | Writes or reuses `{TASK_DIR}/context/user-conventions.snapshot.json` and emits a stage digest path. |
| `show-cache` | Prints the owner's local cache JSON. |

Task snapshots are frozen by default. If the local cache changes during an
active task, the active task sees the update only after an explicit
`memory convention snapshot --refresh`; new tasks use the latest cache.

## Recall V2 Contract

The default memory path requires `mnemos capabilities --json` to advertise JSON
recall and feedback support:

```json
{"commands":{"recall":{"json":true},"feedback":{"json":true}}}
```

Equivalent capability status fields such as `recall_v1=supported` and
`feedback_v1=supported` are accepted. The wrapper passes Recall V2 requests
through as JSON and preserves provider stdout JSON, including status values such
as `ok`, `no_results`, and `degraded`.

Required result fields from a structured Recall V2 backend are:

| Field | Required | Notes |
|---|---:|---|
| `id`, `item_id`, or `memory_id` | yes | Stable item identifier. |
| `content`, `text`, `preview`, or `snippet` | yes | Displayable text. |
| `retrieval_score`, `context_score` | no | Provider-owned scores. Agent Crew does not synthesize replacement relevance scores. |
| `source_path`, `source_section` | no | Source location shown in `context/memory.md` when supplied. |
| `source_content_hash` | no | Mnemos가 캡처한 Markdown 섹션의 SHA-256입니다. 적용 검증이 현재 섹션 내용과 대조합니다. |

Swift 파일의 `source_section`은 선언 이름이나 인자 라벨을 포함한 함수 이름입니다.
예를 들어 `PaletteFocusRequest`와 `keepKey(_:)`를 사용할 수 있습니다. 적용 검증은
`swiftc`로 파일을 구문 분석해 일치하는 선언 하나를 확인합니다. 같은 파일에서 이름이
중복되거나 구문 분석을 실행할 수 없으면 주입에서 제외되고 적용 검증과 피드백도 실패합니다.
`(document)`는 선언을 지정하지 않는 파일 단위 근거입니다.

Agent Crew는 `project_context_section`을 `memory.md`에 넣기 전에 현재 체크아웃의
원본 파일과 섹션을 확인합니다. Markdown 섹션 해시가 있으면 현재 섹션의 해시와
조회 응답 본문을 모두 현재 원본에 대조합니다. 응답 본문만 달라졌다면
`project_recalled_body_mismatch`로 제외되며 원본 문서를 다시 캡처하면 같은 교훈 ID의 본문이 복구됩니다.
제외된 후보는 공급자 응답에 남고 `memory-retrieval.json`의 `diagnostics.source_rejections`에 사유가 기록됩니다.
`Condition`, `Decision`, `Evidence` 필드를 모두 갖춘 교훈은 `memory closeout --verified`가
저장한 근거 해시도 필요합니다. 일반 캡처로 해시 없이 저장하면 `project_evidence_unverified`로
주입과 적용 검증에서 제외됩니다. 해시가 있으면 현재 근거 파일과 줄을 대조합니다.

V2의 `memory-candidates.json`은 주입되지 않은 후보 중 같은 프로젝트와 체크아웃에서
현재 Markdown 섹션을 확인한 최대 5개를 보여 줍니다. 항목은 후보 ID, 검색 순위, 원본 경로와
섹션으로 구성됩니다. 분석자는 원본을 읽어 요청의 조건과 판단이 맞는지 확인합니다.

자동 주입되지 않은 후보를 분석 단계에서 직접 사용한 경우, `memory-usage.json`의
`applied` 결정에 `reason_code: source_reviewed_candidate`와 `source_review`를 기록할 수
있습니다. `excerpt`는 현재 Markdown 섹션 본문의 완전한 줄이고 `relevance`는 그 근거가 현재
판단에 적용되는 이유입니다. 검증기는 조회 후보의 프로젝트·루트, 활성 상태, 섹션 해시,
발췌와 `applications` 위치를 확인합니다. 자동 주입을 나타내는 `memory.md`와 조회 `results`는
이 사용 기록과 독립적으로 유지됩니다.

후보를 직접 확인해 기록한 `applied` 이벤트를 `validated`로 보내려면, 최종 Reviewer가
`REPORT:` 파일에 `MEMORY_USE_APPROVED: <memory_id> <usage_sha256> <retrieval_sha256>`를
남겨야 합니다. 이 확인은 현재 요청, 원본과 적용 위치를 대조한 교훈에만 부여합니다.

확인된 후보의 피드백은 요청 원문, 교훈 ID, 프로젝트·루트, 원본 경로·섹션·내용 해시를 묶은
`reviewed_source_binding`을 전달합니다. 다음 조회에서 공급자가 반환한 결속 값이 모두 일치하고
현재 원본 검사도 통과한 경우에 한해 분석자가 다시 확인하지 않아도 같은 판단을 사용할 수 있습니다.

Default task recall sends the Agent Crew project state key and 10-character
root hash as its primary scope. It also sends `scope.project_context` with
the resolved checkout's directory name and the first 16 hex characters of
the SHA-256 of its absolute path. Capture project documents with that directory
name as `--project-id` and the same checkout as `--project-root`.
Both fields must match to admit an alternate-scope project document. A
source-backed project section in the exact scope can apply to any role or task
shape when the corresponding metadata is absent. Explicit role or shape
metadata must match the request.
Explicit recall scope overrides use the supplied project pair. Application
validation checks the same project scope, and project feedback carries the
matched record's project ID.

Legacy human-readable search output remains available only when
`AGENT_CREW_MEMORY_RECALL_MODE=legacy` or `shadow` is explicitly selected.

## Failure Semantics

Wrapper-observable recall states are `disabled`, `ok`, `no_results`,
`degraded`, `unavailable`, `timeout`, `invalid_json`, and
`incompatible_provider`.

- Missing backend / no-backend mode: print a warning to stderr and exit `0`.
- Recall timeout: bounded wrapper emits `status=timeout` JSON for the default
  V2 path so the caller can proceed without memory.
- Capture timeout: warn and exit `0`; support-memory writes must not block a
  workflow.
- Partial capture failure after local id creation: warn, report the local id
  when detectable, and exit `0`.
- Non-sync capture errors: preserve the backend exit code.
- V2 incompatible provider: emit `status=incompatible_provider` JSON and do
  not fall back to legacy search.
- V2 timeout: emit `status=timeout` JSON and continue unless strict mode is
  enabled.
- V2 invalid provider JSON: emit `status=invalid_json` JSON and continue unless
  strict mode is enabled.

These rules keep agent-crew backend-agnostic while allowing mnemos to evolve its
storage path, FTS schema, metadata, and scoring model independently.
