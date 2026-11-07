# /mr-review-note — GitLab MR review follow-up note composer

## 방법 비교와 트레이드오프

출력을 작성하기 전에 공통 지침 `core/rules/review-method-comparison.md`를 읽고 적용한다.
설치 환경에서는 `~/.agent-crew/rules/review-method-comparison.md`를 읽는다.
실제 방법명, 채택/권장/판단 보류 구분, 선택 이유, 얻는 점·감수할 점, 빈 줄과
`방법별 비교` 소제목, 후보별 설명·장단점, 확인 근거와 한계를 포함한다.
방법명이나 후보 개수를 고정하지 않는다. 방법 선택이 없는 항목에는 비교를 만들지 않는다.
이 형식은 보고서·분석·계획·인계·반영 노트의 서술에 적용하며, 원문 인용과 원시 증거,
프로토콜 필드, 상태·반영률·승인·실행 경계는 바꾸지 않는다.

## Purpose

리뷰 피드백을 반영한 뒤 GitLab MR에 남길 follow-up note를 작성하고, 사용자가 별도로
승인한 경우에만 MR note로 게시한다.

이 command는 단순 감사나 반영률 산출이 아니다. 리뷰 요청, 로컬 반영 근거, 검증 결과,
MR 설명 갱신 여부, 정책 결정 대기 항목을 현재 실행에서 확인한 증거로 대조한 뒤
리뷰어가 바로 상태를 판단할 수 있는 요약 note를 만든다.

## Trigger

- `/mr-review-note`
- `/mr-review-note !249`
- `crew:mr-review-note`
- Codex wrapper: `$mr-review-note`
- 사용자가 MR 리뷰 반영 후 "반영했다는 note", "review follow-up note", "MR에 리뷰
  반영 요약 남겨줘"를 요청한다.

## Skip

- 리뷰 피드백 구현 자체가 필요한 경우에는 구현 workflow를 먼저 사용한다.
- 반영률만 보고하려는 경우에는 `/mr-review-rate`를 사용한다.
- 일반 코드 리뷰가 필요한 경우에는 review workflow를 사용한다.
- MR 설명 생성/갱신만 필요한 경우에는 MR drafting/update workflow를 사용한다.

## Inputs

- `MR_ID`: optional GitLab MR id, URL, or current branch. 없으면 현재 branch의 MR을
  `glab mr view`로 확인한다.
- `REVIEW_SCOPE`: optional. 반영했다고 주장할 리뷰 범위, reviewer, thread, commit, ticket.
- `COMMIT_REF`: optional. 관련 반영 commit. 없으면 현재 branch의 최근 commit과 diff에서
  확인한다.
- `POLICY_WAITING`: optional. 정책 결정 대기 항목이 있으면 원문을 보존한다.
- `OUTPUT_PATH`: optional. note 초안을 로컬 markdown 파일로 저장할 경로.
- `PUBLISH_INTENT`: optional. 사용자가 note 게시를 명시했는지 여부. 명시했어도 원격
  게시 전에는 정확한 note body를 보여주고 별도 게시 승인을 받아야 한다.

## Required Tools And Permissions

- Read: `glab mr view`, `glab mr note list`, `git status`, `git log`, `git diff`, `rg`.
- Optional local verification: 이미 수행된 test/check evidence 확인, 또는 scope에 맞는
  offline/cache-only focused verification.
- Optional local write: 사용자가 `OUTPUT_PATH`를 명시한 경우에만 note draft 저장.
- Remote write with explicit approval only: `glab mr note create`.
- Forbidden without separate explicit approval: `glab mr update`, `git push`, `git commit`,
  `git commit --amend`, `git rebase`, `git merge`, deploy, release.

## Flow

1. Resolve MR target from explicit `MR_ID`, URL, or current branch.
2. Read current MR metadata and notes in this run:
   - `glab mr view <MR_ID>`
   - `glab mr note list <MR_ID>`
3. Identify reviewer feedback atoms. Ignore bot noise, CI chatter, and unrelated discussion unless
   the user explicitly includes them.
4. Inspect local reflection evidence:
   - changed files and diff;
   - related commit messages;
   - test/check output from the current run or visible user-provided evidence;
   - MR description only when checking whether remote MR text was already updated.
5. Classify each note topic for the final message:
   - `REFLECTED`: implemented or otherwise addressed with evidence;
   - `VERIFIED`: test, build, DB/query, parity, or operational evidence actually checked;
   - `UPDATED_MR_DESCRIPTION`: MR description/title was updated and verified;
   - `POLICY_WAITING`: intentionally blocked by product/operation policy decision;
   - `NOT_IN_SCOPE`: explicitly separated from this review follow-up;
   - `UNKNOWN`: evidence is missing, ambiguous, or stale.
6. Preserve the reviewer's original item order and render every meaningful review item with one
   explicit user-facing status marker:
   - `✅ 반영`: the item is fully implemented, documented, or safely adapted with current-run evidence;
   - `⏸️ 미반영`: the item is not fully reflected, including partial, deferred, policy-waiting, or
     out-of-scope outcomes. State exactly what was not changed and why immediately below the item;
   - `❓ 확인 필요`: evidence is missing or ambiguous, so neither reflection nor non-reflection can
     be asserted yet. State the missing evidence immediately below the item.
   Do not collapse several reviewer items into one status, hide unreflected items in a general
   summary, or mark a partially reflected item as `✅ 반영`.
7. Draft one Korean note by default. Preserve commands, paths, API names, statuses, commit ids,
   ticket ids, and quoted reviewer text in the original language.
8. The note must distinguish:
   - 반영한 내용;
   - 검증한 내용;
   - 의도적으로 범위에서 분리한 내용;
   - 정책 결정 대기 또는 blocker;
   - 반영 방식을 고를 때 감수한 트레이드오프 (see "Tradeoff And AI Verification");
   - AI를 사용하며 실행·원본 대조로 확인한 사항 (see "Tradeoff And AI Verification");
   - 관련 commit과 MR description 갱신 여부.
9. Do not claim a DB count, test pass, commit, push, MR description update, or note posting unless
   it was verified in the current run or explicitly supplied by the user as evidence.
10. If posting is requested, show the exact note body and ask for an explicit posting decision
   before remote write.
11. On approval, post a non-resolvable unique status note:

```bash
glab mr note create <MR_ID> --resolvable=false --unique -m "<NOTE_BODY>"
```

For multiline note bodies that are hard to quote safely, use stdin instead:

```bash
printf '%s\n' "<NOTE_BODY>" | glab mr note create <MR_ID> --resolvable=false --unique
```

12. After posting, re-read `glab mr note list <MR_ID>` and report the observed result. Report
    `STATUS: posted` only if `glab` returns explicit success or the newly posted/unique note is
    visible.

## Contract-First Feedback Fidelity

The note must not present "review reflected" as a blanket claim. For each
review topic that the note calls reflected, preserve the reviewer's original
intent, identify the affected contract or side effect, and keep the claim
inside current-run evidence.

When the note claims a review topic is reflected, include the safety status in
reviewer-facing language:

- `contract-safe`: the intended contract still holds or the contract change was approved.
- `parity-safe`: legacy/upstream/downstream behavior was preserved or the divergence is explicit.
- `scope-safe`: the response stayed inside the approved review and task scope.
- `side-effect-safe`: writes, logs, events, persistence, and remote state claims were verified.

If any status is unknown, describe it as missing evidence, policy waiting, or
out of scope before posting or presenting the draft. Do not use the note to
turn `PARTIAL`, `POLICY_WAITING`, `NOT_IN_SCOPE`, or `UNKNOWN` items into
completed work.

## Tradeoff And AI Verification

Reviewers need to see why a suggestion was adopted as-is, adapted, or declined, and what
was checked when an AI coding agent produced or analyzed the change. Include only items
backed by evidence; omit a section instead of padding it.

Evidence sources, in priority order:

1. Decisions, comparisons, and command output from the current run.
2. Decisions the user explicitly supplied.
3. Related commit messages, code comments, and plan/analysis files such as `{TASK_DIR}/context/*`.
4. Anything else is marked `Unverified:` or omitted. Never fill it from memory or guesswork.

Tradeoffs:

- 방법 선택이 필요한 리뷰 항목은 공통 `review-method-comparison` 형식으로 쓴다.
- 한 줄짜리 `선택 / 대안 / 이유 / 비용` 표기로 압축하지 않는다.
- 이미 확인된 결정과 미결정 제안을 구분한다. 부분 반영·기각 상태는 그대로 유지한다.
- 실제 결정·비교 근거가 없는 항목에는 빈 비교 블록을 만들지 않는다.

AI verification:

- Record what the AI generated, suggested, or analyzed that was confirmed by execution or by
  comparison with the source of truth, not the mere fact that AI was used.
- Format: `<확인 대상> — <확인 방법> — <일치 | 불일치 → 수정 | 기각 | 미확인>`.
- Typical cases: AI-proposed code or query validated by tests/DB queries; AI claims about legacy
  behavior, impact, or contracts compared with actual code/docs/API responses; AI suggestions
  rejected or corrected (wrong API or field assumption, scope drift, over-change); boundaries the
  AI was stopped from touching (generated artifacts, out-of-scope modules).
- `미확인` is never phrased as success. Do not repeat the 검증 결과 section verbatim; list only
  checks beyond it.
- Do not include prompt text, internal reasoning, token/cost data, or agent names.

## Note Structure

Use a concise narrative title followed by numbered sections when there are multiple topics.
Keep it reviewer-facing and factual.

노트 본문 마지막에는 반드시 `#### 검증 및 MR 상태` 소제목을 둔다. 방법 비교와
`확인 근거와 한계` 블록 다음에 빈 줄을 두고 작성한다. 이 블록은 방법 비교가 없는
노트에도 포함한다.

- 테스트·검사: 이번 초안 작성에서 실행했는지, 기존 결과만 확인했는지, 실행·확인하지
  않았는지를 명시한다. 실제 실행한 경우에만 명령·범위·결과를 쓰며, 과거 결과를 이번 실행으로 표현하지 않는다.
- 로컬 반영: 코드·커밋 등 확인한 범위에서 반영 여부를 쓴다. 미확인은 그대로 표시한다.
- 원격 MR 반영: 원격 코드 반영 여부와 MR 설명 갱신 여부를 각각 구분한다.
  로컬 반영·커밋만으로 push나 원격 반영을 주장하지 않는다.
- 운영 검증: 확인 여부와 남은 한계를 쓴다. 수행하지 않았으면 미실행 또는 미확인으로 적는다.
- 검증 결과와 MR 상태를 떨어진 문장으로 흩어 놓거나 이 블록을 빈 섹션으로 생략하지 않는다.

```text
리뷰 의견 항목별 반영 결과입니다.

### 1. ✅ 반영 — <리뷰 항목>

- <반영 내용과 근거>

<방법 선택이 있으면 공통 형식의 선택 이유·이해득실·방법별 비교·확인 근거와 한계>

- <잔여 위험 또는 없음>

### 2. ⏸️ 미반영 — <리뷰 항목>

- 미반영 내용: <변경하지 않은 내용>
- 미반영 이유: <계약, 범위, 정책 대기 또는 부작용 근거>

<방법 선택이 있으면 공통 형식. 미반영 상태와 후속 이슈는 유지>

### 3. ❓ 확인 필요 — <리뷰 항목>

- 필요한 근거: <현재 확인할 수 없는 증거>

AI 활용 확인 사항:
- <확인 대상> — <확인 방법> — <일치 | 불일치 → 수정 | 기각 | 미확인>

#### 검증 및 MR 상태

- 테스트·검사: <이번 실행 및 결과 | 기존 결과만 확인 및 출처 | 미실행·미확인>.
- 로컬 반영: <확인한 반영 범위와 근거 | 미확인>.
- 원격 MR 코드 반영: <현재 원격 확인 결과와 근거 | 미확인>.
- MR 설명 갱신: <현재 원격 확인 결과와 근거 | 미확인>.
- 운영 검증: <확인한 범위와 결과 | 미실행·미확인 및 한계>.

관련 반영 커밋: <확인한 commit과 message. 근거가 없으면 미확인>.
```

Omit empty optional sections and empty method-comparison blocks. Keep the required
`검증 및 MR 상태` block even when evidence is unavailable; mark each unavailable result as 미확인.

## Output

Default user-facing output must be readable first and machine-oriented only in a separate
raw/debug mode. Do not expose protocol labels such as `STATUS`, `UNKNOWN`, `ARTIFACTS`,
or approval labels in the default report.

Draft-only or posting decision pending:

```text
MR 리뷰 반영 note 초안을 만들었습니다.

MR: !<id or unknown>
확인한 근거:
- <current-run evidence checked>

[Note 초안]
<review follow-up note>

항목 상태 요약:
- ✅ 반영: <N>건
- ⏸️ 미반영: <N>건
- ❓ 확인 필요: <N>건
- 트레이드오프 기재: <N>건, AI 활용 확인: <N>건 (근거 없는 항목 제외: <N>건)

리뷰 의도/계약 안전성:
- <topic> — contract-safe=<yes|no|unknown>, parity-safe=<yes|no|unknown>, scope-safe=<yes|no|unknown>, side-effect-safe=<yes|no|unknown>, residual risk=<none|details>

아직 확인이 필요한 항목:
- <없음 또는 missing evidence>

다음에 무엇을 할까요?

1. MR에 게시
2. 초안만 유지
3. note 본문 다듬기
4. 취소
```

When the host supports a structured decision surface, render the same four choices through
that surface. The fallback markdown must use ordinary numbered choices such as `1.` and
must not use circled digit characters.

Selection handling:

- `1` posts only after the user has seen the exact note body. Use
  `glab mr note create <MR_ID> --resolvable=false --unique`, then re-read
  `glab mr note list <MR_ID>` before reporting completion.
- `2` keeps the draft only and performs no remote write.
- `3` asks for revision instructions, regenerates the note body, and shows the same choices again.
- `4` stops without posting, saving, or mutating external state.

Posted:

```text
MR note 게시를 확인했습니다.

MR: !<id>
게시 결과: <created | already_exists>
확인한 명령:
- glab mr note list <MR_ID>
저장된 초안: <없음 또는 OUTPUT_PATH>
```

If an automation or parser needs machine-oriented output, expose it only in an explicit
raw/debug mode. If that mode is not implemented, keep the default output human-readable.

## Verification

- `NOTE_BODY` 마지막에 `검증 및 MR 상태` 소제목이 있으며 테스트·검사의 이번 실행 여부,
  로컬 반영, 원격 MR 코드 반영, MR 설명 갱신, 운영 검증 상태가 각각 명시되어 있다.
- 기존 테스트 결과만 확인한 경우와 이번에 직접 재실행한 경우를 구분한다.

- Every reflected claim in `NOTE_BODY` maps to a review atom and current-run evidence.
- Every meaningful reviewer item appears once in original order with `✅ 반영`, `⏸️ 미반영`,
  or `❓ 확인 필요`.
- Every `⏸️ 미반영` item states both what was not changed and why it was not changed.
- Partial reflection is not labeled `✅ 반영`; it remains `⏸️ 미반영` with the reflected subset
  described in the explanation.
- Every policy waiting item is clearly separated from implemented work.
- Every method-comparison block and every `AI 활용 확인 사항` entry maps to an evidence source;
  otherwise it is removed or marked `Unverified:`.
- A tradeoff explanation never turns a partial or declined item into `✅ 반영`.
- AI verification entries end with an explicit result, and `미확인` is not phrased as success.
- Missing evidence is listed under `UNKNOWN`, not phrased as completed work.
- Remote posting happens only after explicit approval and uses `--resolvable=false --unique`.
- After remote posting, the MR note list is checked before reporting `STATUS: posted`.

## Completion

The command completes when it has produced a reviewer-facing note draft with evidence, or when an
approved remote note has been posted and verified.
