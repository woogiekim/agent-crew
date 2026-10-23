# /review-synthesis — Parallel Review Synthesis

## Purpose

Run or collect multiple read-only review lenses in parallel and return one
combined operator-facing report.

This workflow is for receiving synthesis feedback after review-related
commands, skills, agents, and provider-native review capabilities inspect the
same scope from different angles. It does not fix code, post MR notes, update
MR descriptions, commit, push, merge, deploy, or mutate external systems.

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

The synthesis report must list every discovered or configured lens with one of:
`eligible`, `completed`, `not-run`, `suggested`, `blocked`, `degraded`, or
`duplicate-suppressed`. Every finding must preserve its source lens label, and
local implementation status must stay separate from remote MR completion.
Findings from AI system review must keep the host-native source label, for
example `source_lens=codex-system-review`.

When a lens reports caller graph coverage, preserve it in the synthesis instead
of flattening it into a generic finding. Surface BFS inventory, selective DFS
deep dive, `No references found`, partial graph, and unknown graph status with
the source lens. Missing graph coverage must narrow completion guidance rather
than becoming a stronger review or parity claim.

For each non-trivial finding, include `candidate_disposition` and
`implementation_prompt_eligible` in the human-readable report or clearly state
why those fields are `Unknown`. Keep this triage separate from local
implementation status and remote MR completion status.
