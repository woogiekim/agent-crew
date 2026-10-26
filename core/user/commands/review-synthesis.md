# /review-synthesis — Parallel Review Synthesis

## Purpose


Run or collect multiple read-only review lenses in parallel and return one
combined operator-facing report.

This workflow is for receiving synthesis feedback after review-related
commands, skills, agents, and provider-native review capabilities inspect the
same scope from different angles. It does not fix code, post MR notes, update
MR descriptions, commit, push, merge, deploy, or mutate external systems.

## Trigger


- `/review-synthesis <scope>`
- `crew:review-synthesis <scope>`
- The user asks to run review-related commands, skills, or agents in parallel
  and receive a combined result.
- The user asks to combine `$review`, `$post-audit`, `$mr-review-rate`, parity,
  or domain-specific review heuristics into one feedback report.

## Skip


- The user asks for first-pass implementation. Use `crew:run`.
- The user asks for a single generic code review. Use the review workflow.
- The user asks only for MR review reflection rate. Use `mr-review-rate`.
- The user asks only for post-implementation hardening gaps. Use `post-audit`.
- The user asks to post an MR note or update MR metadata directly. Use the
  relevant MR command after explicit approval.

## Inputs

- `REVIEW_SCOPE` - branch, current diff, MR id, file path, module, commit range,
  handoff, or free-text review target.
- `PROJECT_ROOT` - repository root for local review context.
- `BASE_REF` - optional comparison base.
- `MR_ID` - optional GitLab MR id or URL.
- `LENSES` - optional comma-separated lens list. When present it overrides the
  discovered set; when absent the lens set comes from Review Lens Discovery.
  Never hardcode a default list here — a lens declares itself through its own
  review-lens metadata.
- `OUTPUT_PATH` - optional markdown synthesis report path.

## Empty Input Behavior


When the user invokes this command without arguments, do not fail immediately.
Resolve the review scope from the current local repository in this order:

1. If the current directory is inside a git repository and `git status --short`
   shows local changes, use `current working tree changes` as `REVIEW_SCOPE`.
2. If there are no local changes but the current branch has an upstream, use
   `current branch compared with upstream` as `REVIEW_SCOPE`.
3. If an MR can be identified from explicit environment, branch metadata, or
   read-only `glab mr view`, use that MR as additional context and enable the
   MR review-rate lens.
4. If no repository, diff, branch comparison, or MR context can be resolved,
   ask for the missing scope with friendly numbered choices:

```text
검토할 범위를 지정하지 않았습니다. 현재 위치에서 자동으로 잡을 수 있는 변경 범위도 확인되지 않았습니다.

1. MR 번호나 URL을 입력하기
2. 파일 경로, 모듈, 커밋 범위를 입력하기
3. 현재 대화의 특정 리뷰 결과를 붙여넣기
4. 취소
```

If either step 1 or 2 succeeds, continue read-only and state the inferred scope
in the output. Do not ask for confirmation merely because the scope was inferred
from local git state.

## Feedback Triage Boundary


Apply `core/rules/contract-first-feedback-fidelity.md` to every synthesized
finding. In this workflow, review findings are candidate inputs for operator
triage, not accepted implementation requirements.

Do not treat a finding as an approved implementation task. Preserve the source
lens, reviewer or tool wording, affected contract, caller graph status, and
evidence limit before recommending follow-up. If a finding appears actionable,
assign a `candidate_disposition` of `ACCEPT`, `ACCEPT_WITH_ADAPTATION`,
`REJECT_METHOD_ONLY`, `DEFER`, `REJECT`, or `Unknown` and explain the evidence
needed to confirm it.

Only findings whose `candidate_disposition` is `ACCEPT` or
`ACCEPT_WITH_ADAPTATION` may be marked `implementation_prompt_eligible=true`.
`REJECT_METHOD_ONLY`, `DEFER`, and `REJECT` remain valid synthesis outcomes
when backed by contract, parity, scope, side-effect, ownership, or evidence
limits. A synthesis report may recommend a `review-followup` or `prompt` pass,
but it must not silently convert every finding into work.

`candidate_disposition` is the synthesis-time triage value. If the finding is
later promoted into `review-followup` implementation work, carry the same value
into `review-ledger.contract_disposition`; do not reuse
`review-ledger.disposition` for `ACCEPT`-family values. The ledger
`disposition` field remains the lifecycle result (`implemented`, `deferred`,
`rejected`, or `not-applicable`) and may also be displayed through existing
user-facing labels such as `IMPLEMENTED`, `LOCAL_DONE`, or `POLICY_WAITING`.

## Review Evidence Style


Apply `core/rules/review-evidence-style.md` when the review scope is an MR.
Read the MR source branch remotely without checkout, label claims as fact,
`Assumption:`, or `Unverified:`, close decision-critical unknowns with a
confirmation loop and record report corrections, and draft MR notes as
questions with numbered options only. Posting a note stays a separate step that
requires explicit approval of the final draft.

## Review Lens Discovery


Before selecting lenses, run review lens discovery using
`core/scripts/review-lens-discovery.py` or the installed equivalent. Discovery
uses the provider-neutral contract in `core/rules/review-lens-discovery.md`.
When the active host adapter exposes a provider-native review lens manifest,
pass it to discovery with `--host-lens-manifest`; when the adapter sets
`AGENT_CREW_REVIEW_LENS_MANIFEST`, discovery must consume that automatically.
If the active project state contains a host-written `${STATE_DIR}/review-lenses.json`,
pass that manifest to discovery as the host lens manifest.

Discovery must separate installed capability from execution result:

- classify read-only, non-mutating, context-compatible lenses as `eligible`;
- promote an `eligible` lens to `completed` only after it actually runs and
  produces an artifact or inline result in the current synthesis pass;
- report MR-only lenses as `not-run` when MR context is unavailable;
- report parity lenses as `suggested` or `blocked` when the comparison
  contract, source/target repository, or mode is missing;
- report supervisor-only agents such as the system `reviewer` as `blocked`;
- report mutating review follow-up commands as `blocked`;
- report duplicate semantic lenses as `duplicate-suppressed`.

Do not directly invoke the system `reviewer` agent. It is supervisor-spawned.
AI-provided system review participates only as a declared host-native lens such
as `codex-system-review`, and only when its metadata is read-only,
non-mutating, and does not require supervisor context.

## Default Lenses


The default lens set remains:

- generic review;
- post-audit;
- MR review-rate when MR context exists;
- parity when parity or producer/consumer contract scope exists;
- domain/user skills when capability dispatch selects them.

Provider-native lenses may participate only when their metadata declares a
read-only, non-mutating review-lens contract and the host adapter reports them
available.

Include AI system review by default when it is discovered as an eligible
host-native lens such as `codex-system-review`. If the host does not expose a
callable system review surface, keep the lens `not-run` or `degraded` with the
adapter reason instead of fabricating a completed result.
When a discovered host-native lens includes runner metadata, the active host
adapter is responsible for applying that runner to the same read-only review
scope and preserving the lens source label in the synthesized output.

Prior parity output from an earlier session or branch is a trigger candidate
only, never current evidence. Refresh it against the current repository state,
or report the lens as `suggested`. Do not report it as `completed` unless this
run actually rechecked the contract. If a parity signal exists but the
comparison contract, source/target repository, or mode is missing, report
`blocked` with the missing scope instead of guessing.

## Required Tools And Permissions


- Read/local tools: `git status`, `git diff`, `git log`, `rg`, file reads.
- Optional GitLab read tools: `glab mr view`, `glab mr note list` when MR context
  is available.
- Optional project-local verification tools may be suggested by the underlying
  review lenses, but the synthesis command must not claim they passed unless
  they actually ran.
- Forbidden without separate explicit approval: code edits, `git add`, `git
  commit`, `git push`, `git merge`, `git rebase`, `glab mr update`, `glab mr note
  create`, deployment, release, destructive cleanup.
- Review lens discovery: `core/scripts/review-lens-discovery.py` or the
  installed equivalent, plus read access to the host lens manifest.

## Parallel Fan-out

Running the lenses one after another is the main cost of this workflow, and a
serial pass tempts the operator to narrow the lens set. Decide the dispatch mode
from host capabilities, never from the host's name.

Read `agent_background` from `${STATE_DIR}/capabilities.json`
(`core/rules/capabilities/agent-background.md`). Absent file or absent flag
means `false` — legacy behavior.

**`agent_background: true` — concurrent dispatch.** Issue every eligible lens in
a *single* dispatch so the host can run them at once. Issuing them one call at a
time is sequential execution wearing a parallel label, no matter how the report
describes it. Each lens is one unit of work with its own prompt and its own
artifact path.

**`agent_background: false` — sequential dispatch.** Run the eligible lenses in
`lens_id` order and say so in the report. Do not silently drop lenses to save
time; a lens the operator expected must appear with a status, not vanish.

**Host-native lenses** carry `runner` metadata and belong to the adapter, not to
this command. Pass them the same read-only scope and let the adapter apply the
runner. A runner that cannot be driven concurrently runs alongside the batch as
its own unit; that does not make the whole pass sequential.

### Rules that hold in either mode

- **Isolation.** Each lens writes only its own artifact under
  `TASK_DIR/context/review-synthesis/`. No lens writes another lens's file, and
  nothing writes a shared aggregate until every unit has settled.
- **Failure containment.** One lens erroring, timing out, or returning an
  unusable result marks *that lens* `degraded` with a reason. It never fails the
  pass and never cancels its siblings.
- **Per-lens budget.** Honor each lens's `timeout_seconds`. Exceeding it yields
  `degraded` with reason `lens_timeout` and whatever partial output exists —
  never a fabricated completion.
- **Deterministic report order.** Order findings by `lens_id`, never by
  completion order. Two runs over the same scope must read the same way.
- **Read-only is unchanged.** Concurrency grants no new permission. Every unit
  inherits the Required Tools And Permissions boundary.
- **No cross-lens leakage.** A lens must not receive another lens's findings as
  input. They inspect the same scope from different angles; feeding one into
  another collapses them into a single viewpoint.

The report states which mode ran and how many units were dispatched, so a
suspiciously fast or slow pass can be explained without rerunning it.

## Flow

1. Resolve scope and lens set.
   - Preserve `REVIEW_SCOPE` as the root input.
   - If `REVIEW_SCOPE` is empty, apply Empty Input Behavior before selecting
     lenses.
   - Infer whether MR context exists from `MR_ID`, branch metadata, or `glab mr
     view` read-only output.
   - Run Review Lens Discovery to obtain the candidate lens set, passing the
     host lens manifest when the adapter provides one. Apply `LENSES` as an
     override on top of the discovered set.
   - If no lens is `eligible`, report `STATUS: blocked` and ask for a narrower
     scope.

2. Dispatch every eligible lens per Parallel Fan-out.
   - Generic code review lens: independent read-only review over the current
     branch, path, commit, or range.
   - Post-audit lens: read-only aftercare and hardening audit over the same
     implemented surface.
   - MR review-rate lens: read-only reflection-rate audit only when MR context
     is present.
   - Parity lens: only when the request or scope asks for parity or a
     producer/consumer contract comparison.
   - Domain skill lens: only when capability dispatch or explicit user context
     selects a domain-specific review skill.
   - Host-native lens: only through its declared runner, and only when its
     metadata is read-only, non-mutating, and needs no supervisor context.
   - A lens is promoted from `eligible` to `completed` only after it actually
     produces a result in this pass.

3. Write each lens output as an artifact.
   - Recommended paths under `TASK_DIR/context/review-synthesis/`:
     - `generic-review.md`
     - `post-audit.md`
     - `mr-review-rate.md`
     - `parity.md`
     - `domain-skill.md`
     - `<lens_id>.md` for any discovered or host-native lens
   - A missing optional lens is recorded with its discovery status and reason.
   - Do not create blank proof templates.

4. Delegate aggregation to `review-synthesis-coordinator`.
   - Pass `REVIEW_ARTIFACTS`, `REVIEW_SCOPE`, `PROJECT_ROOT`, `BASE_REF`, and
     `MR_ID`.
   - The coordinator reads the artifacts and produces the final synthesis.
   - Preserve each lens's caller graph coverage instead of flattening it into a
     generic finding. If a lens reports BFS inventory, selective DFS deep dive,
     `No references found`, partial graph, or unknown graph status, surface that
     status with the lens result and keep it out of stronger completion claims.
   - Assign `candidate_disposition` per Feedback Triage Boundary before any
     finding is offered as follow-up work.

5. Return next-action choices.
   - Choices are suggestions only. They must not execute mutation inside this
     workflow.

## 보고 분량


읽는 사람이 한 화면에서 판단할 수 있어야 한다. 길이는 성실함의 증거가 아니다.

- 항목 한 건 = 제목 한 줄 + 근거 한 줄. 두 줄을 넘기지 않는다. 설명 문단을 쓰지 않는다.
- 근거는 `file:line` 으로 쓴다. 코드 인용은 판단에 꼭 필요할 때만 3줄 이내.
- `반드시 봐야 할 문제` 최대 5건, `주의할 항목` 최대 7건. 넘치면 `그 외 N건` 한 줄로 접고
  전체 목록은 아티팩트 경로로 넘긴다. 접었다는 사실을 반드시 적는다.
- 내용 없는 섹션은 `없음` 한 줄로 쓴다. 빈 템플릿을 남기지 않는다.
- 같은 사실을 요약과 항목에 두 번 쓰지 않는다.
- 전체 보고서는 80줄을 넘기지 않는다. 넘치면 항목 수를 줄인다. 문장을 줄여서 맞추지 않는다.

상세 서술이 필요한 항목은 보고서에 한 줄로 두고, 본문은 렌즈 아티팩트
(`TASK_DIR/context/review-synthesis/<lens>.md`) 에 둔 뒤 경로만 가리킨다.

## 선택지 표기


보고서와 노트 초안에서 선택지를 제시할 때는 아래를 지킨다.

- 마크다운 번호 목록(`1.` `2.` `3.`)으로 쓰고, 한 선택지는 한 항목으로 둔다.
- `①②③` 같은 원문자를 쓰지 않는다. GitLab·GitHub 마크다운은 원문자를 목록 기호로 보지 않아
  줄바꿈이 무시되고 선택지 전체가 한 문단으로 붙는다.
- 목록 앞에는 빈 줄을 둔다. 빈 줄이 없으면 앞 문단에 흡수된다.
- 선택지 한 건은 한 줄(약 60자)로 끝낸다. 이유·근거는 선택지가 아니라 본문에 둔다.

## Output

```text
리뷰 종합 결과입니다.

범위: <scope>
기준: <base/ref/MR/current diff/unknown>
실행 방식: <concurrent|sequential>, 디스패치 <N>건
실행한 렌즈:
- <lens> — <eligible|completed|not-run|suggested|blocked|degraded|duplicate-suppressed>

반드시 봐야 할 문제:  (최대 5건, 한 건 2줄 이내)
- <finding> — <lens>, <file:line>, <candidate_disposition>

주의할 항목:  (최대 7건, 한 건 2줄 이내)
- <finding> — <lens>, <file:line>, <candidate_disposition>

리뷰 반영 상태:
- 로컬 반영: <rate or not-run>
- MR 전체 반영: <rate or not-run>
- remote write 필요: <none or exact approval-needed action>

렌즈 간 충돌/차이:
- <conflict or none>

확인한 것:
- <files, commands, artifacts actually checked>

확인하지 않은 것:
- <items not checked and why>

Caller graph coverage:
- <lens> — <completed|partial|No references found|unknown|not_applicable>

다음에 무엇을 할까요?

1. 부족 항목을 구현 workflow로 넘기기
2. MR note/description 초안 만들기
3. 특정 렌즈만 다시 실행하기
4. 보고서만 유지
5. 종료
```

Selection handling:

- `1` returns the smallest execution prompt or logical intent for a separate
  implementation workflow, carrying only findings whose
  `candidate_disposition` is `ACCEPT` or `ACCEPT_WITH_ADAPTATION`. It must not
  edit files inside this read-only command.
- `2` drafts an MR note/description prompt only. Posting/updating requires a
  separate explicit approval.
- `3` asks for the lens to rerun and keeps the action read-only.
- `4` returns the synthesis report only.
- `5` stops without further action.

The report must list every discovered or configured lens with one of
`eligible`, `completed`, `not-run`, `suggested`, `blocked`, `degraded`, or
`duplicate-suppressed`. Every finding must preserve its source lens label, and
local implementation status must stay separate from remote MR completion.
Findings from AI system review must keep the host-native source label, for
example `source_lens=codex-system-review`.

For each non-trivial finding, include `candidate_disposition` and
`implementation_prompt_eligible` in the human-readable report, or clearly state
why those fields are `Unknown`. Keep this triage separate from local
implementation status and remote MR completion status.

## Completion

The command completes when it produces a synthesis report that:

- lists every discovered or configured lens with its discovery status;
- labels every finding by source lens, including host-native lenses;
- assigns `candidate_disposition` and `implementation_prompt_eligible` to every
  non-trivial finding, or states why they are `Unknown`;
- separates local implementation status from remote MR status;
- keeps each finding within two lines and the whole report within 80 lines;
- renders choices as a `1.` markdown list with no circled digits;
- preserves unknowns and caller graph coverage;
- states the fan-out mode and the number of dispatched units;
- performs no source, git, deployment, or MR remote mutation.

