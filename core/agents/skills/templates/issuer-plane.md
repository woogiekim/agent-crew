# issuer-plane — Plane Backend Adapter

This skill implements the `issuer` agent's Adapter Interface Contract for the
**Plane** project management backend. It is loaded by the `issuer` dispatcher when
`BACKEND_ADAPTER=plane` (the default).

All six interface steps (Step 0 through Step 5) are defined below, plus a
pre-publication preview gate before any create call.

## Tools Required

| Tool | Purpose |
|---|---|
| `mcp__plane__get_me` | Verify authentication and get current user |
| `mcp__plane__list_projects` | Resolve project ID from name, validate ID, or present interactive project selection |
| `mcp__plane__get_project_members` | Resolve assignee emails/names to member UUIDs |
| `mcp__plane__list_states` | Map state names to state UUIDs |
| `mcp__plane__list_labels` | Check which labels already exist |
| `mcp__plane__create_label` | Create missing labels before referencing them |
| `mcp__plane__list_work_items` | Duplicate detection before creating each work item |
| `mcp__plane__create_work_item` | Publish each parsed issue as a work item |
| `mcp__plane__update_work_item` | Update state, labels, assignees, or description of existing work items |
| `mcp__plane__retrieve_work_item` | Fetch canonical URL for the summary table |
| `mcp__plane__retrieve_work_item_by_identifier` | Resolve issue by project identifier + sequence number (e.g. ENRTC-273) |
| `mcp__plane__search_work_items` | Find work items by title or keyword for lifecycle operations |
| `mcp__plane__create_work_item_comment` | Append a comment to an existing work item (lifecycle update / status notes) |
| `mcp__plane__list_work_item_comments` | Inspect existing comments before creating a duplicate or appending |
| `mcp__plane__delete_work_item` | Delete a work item (requires explicit user confirmation — destructive) |

## Inputs (Plane-specific)

In addition to the abstract inputs (`ISSUES_FILE`, `DRY_RUN`, `TASK_DIR`),
the Plane adapter accepts:

- `PLANE_WORKSPACE_SLUG` (or `WORKSPACE_SLUG`) — Plane workspace slug (e.g. `my-org`).
  Falls back to the `PLANE_WORKSPACE_SLUG` environment variable. **Required.**
- `PLANE_PROJECT_ID` (or `PROJECT_ID`) — UUID of the target Plane project.
  If omitted along with `PLANE_PROJECT_NAME`, interactive project selection is triggered.
- `PLANE_PROJECT_NAME` (or `PROJECT_NAME`) — Human-readable project name used to
  resolve `PLANE_PROJECT_ID` when the UUID is not known.

Input resolution priority for workspace slug:
1. `PLANE_WORKSPACE_SLUG` input parameter
2. `WORKSPACE_SLUG` input parameter
3. `PLANE_WORKSPACE_SLUG` environment variable
4. (error if none of the above)

---

## Step 0 — Authenticate and resolve project

1. Resolve `PLANE_WORKSPACE_SLUG`:
   - Use `PLANE_WORKSPACE_SLUG` if provided as input.
   - Otherwise use `WORKSPACE_SLUG` if provided.
   - Otherwise read from the `PLANE_WORKSPACE_SLUG` environment variable.
   - Do NOT attempt to derive the slug from any API response — it must come
     from the input or environment only (API responses may return internal IDs,
     not the slug).
   - If still absent, abort with:
     `ERROR: PLANE_WORKSPACE_SLUG is required. Provide it as input or set the environment variable.`

2. Call `mcp__plane__get_me` to confirm the authenticated user and print:
   `Authenticated as: {display_name} ({email})`.

3. Call `mcp__plane__list_projects` (workspace=`PLANE_WORKSPACE_SLUG`) to
   retrieve all projects.

4. Resolve the target project using the following priority order:

   **Case A — `PLANE_PROJECT_ID` (or `PROJECT_ID`) is provided:**
   - Verify it appears in the project list.
   - If not found, abort with:
     `ERROR: Project id="{PLANE_PROJECT_ID}" not found in workspace "{PLANE_WORKSPACE_SLUG}". Available projects: {list}`.

   **Case B — Only `PLANE_PROJECT_NAME` (or `PROJECT_NAME`) is provided (no ID):**
   - Find the project whose `name` matches (case-insensitive) and store its
     `id` as `PLANE_PROJECT_ID`.
   - If not found, abort with:
     `ERROR: Could not find project "{PLANE_PROJECT_NAME}" in workspace "{PLANE_WORKSPACE_SLUG}". Available projects: {list}`.

   **Case C — Neither `PLANE_PROJECT_ID` nor `PLANE_PROJECT_NAME` is provided:**
   - Filter the project list to projects where the authenticated user is a
     member (`network` or `member` field confirms membership).
   - If no member projects are found, abort with:
     `ERROR: No accessible projects found in workspace "{PLANE_WORKSPACE_SLUG}".`
   - Present the list via `AskUserQuestion` (interactive project selection):
     - header: "Select Project"
     - question: "Which Plane project should issues be published to?"
     - options: one option per project, label = project name, description = `id={project_id}`
   - Store the selected project's `id` as `PLANE_PROJECT_ID` and its `name`
     as `PLANE_PROJECT_NAME`.

5. Print: `Target project: {project.name} (id={PLANE_PROJECT_ID})`.

6. Emit the `TARGET_SUMMARY:` block for the dispatcher's Step 0.5:
   ```
   TARGET_SUMMARY:
     backend: plane
     project_name: {PLANE_PROJECT_NAME}
     project_id: {PLANE_PROJECT_ID}
     workspace_slug: {PLANE_WORKSPACE_SLUG}
   ```
   This block MUST be emitted before any mutating call. The dispatcher reads
   it verbatim to present the confirmation screen in Step 0.5.

---

## Step 0.6 — Local issue template (per-project, optional)

Some Plane projects need a stable issue body structure. The Plane adapter uses
local templates for those projects instead of depending on a remote template
issue during publication. This keeps issue creation deterministic when Plane
lookup, permissions, MCP availability, or network state is degraded.

### Project local-template registry

| `PLANE_PROJECT_IDENTIFIER` | Local template | Required labels (apply by default) |
|---|---|---|
| `ENRTC` (project_id 70b5c55a-7246-4a33-8996-c037d7620db7) | ENRTC default issue template | one of: 플랫폼전환 / 앱개발 / 에누리FE / 에누리BE / 운영 |

Add a new row here when another project adopts a local template.

### ENRTC default issue template

For `ENRTC`, use the local canonical ENRTC template below. Do not read
`ENRTC-1` during normal create or update publication. `ENRTC-1` may be used by
a separate maintenance or drift-check task, but it is not part of the runtime
publication path.

Preserve all section headings (🔖 기본 정보, 📋 요청 정보, 📌 요청 내용,
✅ TODO List, ✔ Check List, 📝 진행 내역, 🚨 이슈 트래킹) and their bullet
structure. Replace placeholder values with the per-issue content parsed in
Step 1; leave sections that have no input as explicit `Unknown` or `MISSING`
entries instead of deleting entire sections or inventing details.

```markdown
## 🔖 기본 정보

**업무 구분:** [ ] 운영 [ ] 신규 개발 [ ] 개선 [ ] 인프라 [ ] 데이터
**우선순위:** P1 / P2 / P3
**예상 M/D:** Unknown

---

## 📋 요청 정보

- **요청자:** Unknown
- **기획자:** Unknown
- **관련 시스템:** Unknown
- **목적:** MISSING
- **구현 범위:** MISSING
- **테스트 기준:** MISSING
- **브랜치 유형:** MISSING
- **권장 브랜치:** MISSING

### 📌 요청 내용

#### 요약

- 사용자가 원하는 결과와 이유를 짧게 작성한다.

#### Background

- 배경, 문제 상황, 관련 리뷰/이슈/요청을 작성한다.

#### Current Behavior

- 현재 동작 또는 현재 제약을 작성한다.

#### Target Behavior

- 변경 후 기대 동작을 작성한다.

#### Scope

- 포함 범위, repository, module, endpoint, service, 주요 파일을 작성한다.

#### Out of Scope

- 이번 이슈에서 하지 않을 일을 작성한다.

#### Implementation Notes

- 구현 메모(개발자용): 코드 식별자, dependency, migration note, 운영상 주의점을 작성한다.

#### Branch / Commit Convention

- branch type은 git/conventional commit 의도에 맞춰 선택한다.
- 기본 branch name 형식은 `{type}/{issue-key}-{short-slug}`로 작성한다.
- `feat`: 새로운 사용자-facing 기능, 제품 동작, capability 추가.
- `fix`: 버그, 회귀, 잘못된 동작, 장애 원인 수정.
- `refactor`: 외부 동작 변화 없는 내부 구조 개선.
- `docs`: 문서만 변경.
- `test`: 테스트만 추가하거나 수정.
- `chore`: tooling, build, config, maintenance 등 제품 동작과 직접 무관한 작업.
- 필요하면 `perf`는 성능 개선, `ci`는 CI/CD workflow 변경에 사용한다.
- 여러 성격이 섞이면 주된 변경 목적을 branch type으로 선택하고 보조 범위는
  Implementation Notes에 남긴다.
- 판단 근거가 부족하면 branch type 또는 branch name을 `MISSING`으로 남기고
  임의로 만들지 않는다.

#### Contract / Parity

- producer/consumer 관계, API, DB, schema, DTO, parity 확인 필요 여부를 작성한다.

#### Test Plan

- 단위 테스트, 통합 테스트, 수동 확인, offline 우선 여부를 작성한다.

#### Rollout / Rollback

- 배포 영향, 롤백 가능성, 모니터링 포인트를 작성한다.

#### Open Questions

- Unknown, MISSING, blocker, 정책 결정 대기 항목을 작성한다.

---

# ✅ TODO List

[ ] **문제 정의 및 분석**

- Background와 Current Behavior를 확인한다.

[ ] **설계 정리**

- Scope, Out of Scope, Contract / Parity를 정리한다.

[ ] **코드 수정 / 개발**

- Implementation Notes 기준으로 변경한다.

[ ] **개발 테스트**

- Test Plan 기준으로 검증한다.

[ ] **운영 배포**

- Rollout / Rollback 기준으로 확인한다.

---

# ✔ Check List

[ ] 목적이 명확함
[ ] 구현 범위가 명확함
[ ] 브랜치 유형과 권장 브랜치명이 명확함
[ ] 기대 동작이 명확함
[ ] 테스트 기준이 명확함
[ ] Unknown, MISSING, blocker, 정책 결정 대기 항목이 있으면 명시됨
[ ] 운영 영향도 확인 (Kafka / DB / 외부 API 등)
[ ] 트래픽 영향 여부 검토
[ ] 롤백 시나리오 확보
[ ] 모니터링 포인트 정의
[ ] 관련 팀 공유 완료

---

# 📝 진행 내역

### 📅 YYYY/MM/DD

- 작업 내용 기록
- 이슈 발생 시 내용 정리

---

# 🚨 이슈 트래킹

- 발생 이슈:
- 원인:
- 조치 내용:
- 재발 방지 대책:
```

### How to apply

1. After Step 0 authentication, check the table above for the current
   `PLANE_PROJECT_IDENTIFIER`.

2. If the current project has a local template row, compose
   `description_html` from that local template. Do not collapse the body to raw
   `<p>{text}</p>`.

3. Insert Step 1 content with this deterministic mapping:
   - `Description` / issue summary / spec text → `📌 요청 내용` → `요약`
   - `Background` → `📌 요청 내용` → `Background`
   - `Current Behavior` → `📌 요청 내용` → `Current Behavior`
   - `Target Behavior` → `📌 요청 내용` → `Target Behavior`
   - `Scope` → `📌 요청 내용` → `Scope`
   - `Out of Scope` → `📌 요청 내용` → `Out of Scope`
   - `Implementation Notes` → `📌 요청 내용` → `Implementation Notes`
   - `BranchType` / `Branch Type` → `📋 요청 정보` → `브랜치 유형`
   - `BranchName` / `Branch Name` / `Recommended Branch` → `📋 요청 정보` → `권장 브랜치`
   - `Branch / Commit Convention` / `Branch Naming` → `📌 요청 내용` →
     `Branch / Commit Convention`
   - `Contract / Parity` → `📌 요청 내용` → `Contract / Parity`
   - `Test Plan` → `📌 요청 내용` → `Test Plan`
   - `Rollout / Rollback` → `📌 요청 내용` → `Rollout / Rollback`
   - `Open Questions` → `📌 요청 내용` → `Open Questions`
   - `Acceptance Criteria` → `✅ TODO List` as additional unchecked items

4. Missing implementation-critical fields stay visible as `Unknown` or
   `MISSING`. Do not manufacture project names, files, tests, owner decisions,
   runtime evidence, or rollout details just to fill the template.

5. In Step 4's `mcp__plane__create_work_item` (and any `update_work_item`), the
   `description_html` field MUST be the rendered local-template body. If
   `description_html` is not accepted, send markdown plaintext that preserves
   the same local-template sections.

6. For projects NOT in the local-template registry, Step 4 behaves as before
   (free-form `<p>{full_description}</p>`).

### Required-label rule (when template specifies labels)

If the pin registry row lists "Required labels", the issuer MUST select **at
least one** of the listed labels and attach it to every created/updated issue,
even when the input markdown does not specify a label. Selection heuristic:

- BE work (Spring/Kotlin/Java backend) → `에누리BE`
- FE work (Next.js/JSP/Vue/React) → `에누리FE`
- Mobile app work → `앱개발`
- Operational / config / monitoring → `운영`
- Cross-cutting platform migration → `플랫폼전환`

When multiple labels are warranted (e.g., a FE+BE feature) attach both.

### Update vs create

The template rules apply identically to update operations
(`mcp__plane__update_work_item`). When updating existing issues that lack the
template skeleton, the issuer should backfill the body to match the template
unless explicitly told otherwise by the user prompt.

---

## Supplementary Writing Guideline — Plain Lead + Developer Details

This guideline mirrors the core `issuer` dispatcher and is supplementary. The
Plane adapter's local issue templates, field mappings, preview table, mutation
gates, lifecycle summaries, and summary table format remain authoritative.
Apply the rule below inside issue body prose and body excerpts without changing
the adapter's required structure.

1. **Plain-language summary first.** Start issue descriptions with short,
   outcome-focused sentences that any non-technical reader can understand
   without repository context. Avoid file paths, code identifiers, class or
   function names, command lines, branch names, schema names, and internal
   implementation jargon in the lead section.
2. **Developer details are separate.** Move engineer-only details into a
   clearly separated developer-detail subsection. The recommended heading is
   `구현 메모(개발자용)`; an equivalent heading such as
   `Implementation notes for developers` is acceptable when the issue body's
   base language or project template calls for it.
3. **No audience-role labels for the plain summary.** A developer-detail
   separator is allowed because it describes the content type. Do not label the
   plain-language lead with role-targeting audience labels such as
   `기획자용`, `기획자 요약`, `for planners`, `for designers`, or similar
   role-specific labels.

Recommended structure inside a Plane issue body:

```markdown
### 요약
This change makes the requested work clear to readers who need the outcome.

### 구현 메모(개발자용)
- Updates `path/to/file.ext` and sends `{api_field}` in the Plane payload.
```

---

## Step 1 — Parse the issues file

1. Read `ISSUES_FILE` using the filesystem tool.

2. Split the file on `## ` headings. Each segment becomes one candidate issue.

3. For each segment, extract:
   - `title`: the text of the `##` heading line (trimmed).
   - `priority`: value from the `**Priority:**` line (normalise to lowercase:
     `urgent` | `high` | `medium` | `low` | `none`). Default: `none`.
   - `state_name`: value from the `**State:**` line (trimmed). Default: `Todo`.
   - `labels_raw`: comma-separated values from the `**Labels:**` line. Default: `[]`.
   - `assignees_raw`: comma-separated values from the `**Assignees:**` line. Default: `[]`.
   - `start_date`: value from the `**StartDate:**` line (ISO format YYYY-MM-DD). Default: `null`.
   - `due_date`: value from the `**DueDate:**` line (ISO format YYYY-MM-DD). Default: `null`.
   - `estimate`: integer value from the `**Estimate:**` line. Default: `null`.
   - `description`: all text under `### Description` up to the next `###` or
     end of segment.
   - `acceptance_criteria`: all text under `### Acceptance Criteria` up to the
     next `###` or end of segment.
   - `background`: all text under `### Background`.
   - `current_behavior`: all text under `### Current Behavior`.
   - `target_behavior`: all text under `### Target Behavior`.
   - `scope`: all text under `### Scope`.
   - `out_of_scope`: all text under `### Out of Scope`.
   - `implementation_notes`: all text under `### Implementation Notes`.
   - `branch_type`: value from the `**BranchType:**`, `**Branch Type:**`, or
     `**브랜치 유형:**` line. Default: `MISSING`.
   - `branch_name`: value from the `**BranchName:**`, `**Branch Name:**`,
     `**Recommended Branch:**`, or `**권장 브랜치:**` line. Default: `MISSING`.
   - `branch_commit_convention`: all text under
     `### Branch / Commit Convention` or `### Branch Naming`.
   - `contract_parity`: all text under `### Contract / Parity`.
   - `test_plan`: all text under `### Test Plan`.
   - `rollout_rollback`: all text under `### Rollout / Rollback`.
   - `open_questions`: all text under `### Open Questions`.
   - `full_description`: concatenation of `description` and (if non-empty)
     each recognized implementation-ready section, followed by an `##
     Acceptance Criteria` section appended from `acceptance_criteria` when
     present.

   These implementation-ready sections are optional in input, but the ENRTC
   local template keeps their destination headings visible. Missing values are
   represented as `Unknown` or `MISSING`; do not invent details.

4. Skip segments with an empty title and log a warning:
   `WARN: Skipping segment with no title (content preview: {first 80 chars})`.

5. Print: `Parsed {N} issues from {ISSUES_FILE}`.

**Field reference (Plane work item schema mapping):**

| Abstract field | Plane API field | Notes |
|---|---|---|
| `Priority` | `priority` | `urgent` / `high` / `medium` / `low` / `none` |
| `State` | `state` (UUID, resolved by name) | Any state name configured in the project |
| `Labels` | `label_ids` (UUIDs, resolved by name) | Comma-separated label names |
| `Assignees` | `assignee_ids` (UUIDs, resolved by email/display_name) | Comma-separated member emails or display names |
| `StartDate` | `start_date` | ISO date YYYY-MM-DD |
| `DueDate` | `target_date` | ISO date YYYY-MM-DD |
| `Estimate` | `estimate_point` | Integer point value |
| `Background` | `description_html` section | Background, problem context, related review or issue |
| `Current Behavior` | `description_html` section | Current behavior or constraint |
| `Target Behavior` | `description_html` section | Expected behavior after change |
| `Scope` | `description_html` section | Included repositories, modules, files, endpoints, services |
| `Out of Scope` | `description_html` section | Explicit exclusions |
| `Implementation Notes` | `description_html` section | Developer details, dependencies, migration notes |
| `BranchType` | `description_html` section | Conventional commit type for the recommended branch |
| `BranchName` | `description_html` section | Recommended branch name, normally `{type}/{issue-key}-{short-slug}` |
| `Contract / Parity` | `description_html` section | Producer/consumer, API, DB, schema, DTO, parity needs |
| `Test Plan` | `description_html` section | Unit/integration/manual checks and offline preference |
| `Rollout / Rollback` | `description_html` section | Deployment impact, rollback, monitoring |
| `Open Questions` | `description_html` section | Unknowns, blockers, policy decisions |

---

## Step 2 — Resolve or create labels

1. Call `mcp__plane__list_labels` (workspace=`PLANE_WORKSPACE_SLUG`,
   project=`PLANE_PROJECT_ID`) to get existing labels.

2. Build a map: `label_name_lower → label_id`.

3. For each unique label name across all parsed issues:
   - If found in the map → use the existing `id`.
   - If not found → call `mcp__plane__create_label` with `name={label_name}` and
     a default colour (`#6366f1`). Store the returned `id` in the map.
   - If `DRY_RUN=true` → skip creation; log `DRY_RUN: would create label "{label_name}"`.

4. For each issue, replace `labels_raw` with a list of resolved `label_id` UUIDs.

---

## Step 2b — Resolve assignee IDs

1. Call `mcp__plane__get_project_members` (workspace=`PLANE_WORKSPACE_SLUG`,
   project=`PLANE_PROJECT_ID`) to get project members.

2. Build a map: `email_lower → member_id` and `display_name_lower → member_id`.

3. For each unique assignee value across all parsed issues:
   - Try email match first (case-insensitive), then display_name match.
   - If found → store the `member_id` UUID.
   - If not found → log a warning: `WARN: Assignee "{value}" not found in project members — skipping.`
   - If `DRY_RUN=true` → skip resolution; log `DRY_RUN: would resolve assignee "{value}"`.

4. For each issue, replace `assignees_raw` with a list of resolved member UUID strings.

---

## Step 3 — Resolve state IDs

1. Call `mcp__plane__list_states` (workspace=`PLANE_WORKSPACE_SLUG`,
   project=`PLANE_PROJECT_ID`).

2. Build a map: `state_name_lower → state_id`.

3. For each issue, look up `state_name.lower()` in the map:
   - If found → store `state_id`.
   - If not found → log a warning and fall back to the first state whose `group`
     is `"backlog"` or `"unstarted"`. If no fallback exists, omit `state_id`.

4. Print the resolved state map for transparency:
   ```
   States available: Todo (id=...), Backlog (id=...), In Progress (id=...), Done (id=...)
   ```

---

## Step 3.5 — Preview resolved issues

1. Build a preview table from the resolved issue set after Steps 1-3 complete.
   For template-backed projects, also build an implementation readiness warning
   summary. The readiness check is informational and must not invent evidence.

   Implementation readiness checks:
   - `purpose` — description or summary states the desired outcome.
   - `implementation scope` — `Scope` or equivalent body text identifies the
     included surface.
   - `expected behavior` — `Target Behavior` or equivalent body text states the
     expected behavior.
   - `branch convention` — branch type and recommended branch name are present,
     or explicit `MISSING` markers remain visible.
   - `test plan` — `Test Plan` or acceptance criteria define verification.
   - `unknowns/blockers` — `Open Questions` or explicit `Unknown` / `MISSING`
     entries are visible when information is unavailable.

   Missing checks are preview warnings, not automatic blockers. The user may
   still approve publication, but the body must retain `Unknown` or `MISSING`
   markers rather than hiding gaps.

2. Print a concise preview before any create call:
   ```
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   issuer — Preview
   Project  : {project.name}
   Workspace: {PLANE_WORKSPACE_SLUG}
   Backend  : plane
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   | # | Title | Priority | State | Labels | Assignees | Start | Due | Estimate | Body preview |
   |---|---|---|---|---|---|---|---|---|---|
   | 1 | {title} | {priority} | {state_name} | {labels} | {assignees} | {start_date} | {due_date} | {estimate} | {body_excerpt} |
   ...
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Implementation readiness:
   - purpose: <ok|MISSING>
   - implementation scope: <ok|MISSING>
   - expected behavior: <ok|MISSING>
   - branch convention: <ok|MISSING>
   - test plan: <ok|MISSING>
   - unknowns/blockers: <ok|MISSING|none-declared>
   ```
   Use a short body excerpt (for example the first 120 characters) so the
   preview stays readable.

3. If `DRY_RUN=true`, skip the confirmation prompt and continue directly to
   Step 4's dry-run payload output.

4. Otherwise present the preview via `AskUserQuestion` when structured user
   choice UI is available:
   - header: "Preview Issue Publication"
   - question: the preview block above
   - options:
     - `[A] Approve — proceed with publication`
     - `[B] Cancel — stop, do not publish`

   Plain terminal fallback:

   ```
   Proceed with publication? [Y/N]:
   ```

5. If the user cancels, halt immediately with:
   ```
   STATUS: BLOCKED
   BLOCKER: user_cancelled_preview_confirmation
   DETAIL: User declined the previewed issue set. No issues were published.
           Re-run with the correct issue list and confirm when prompted.
   ```

---

## Step 4 — Create work items

If `DRY_RUN=true`:
- For each issue, print the resolved payload that would be sent:
  ```
  DRY_RUN [N/{total}] "{title}" | priority={priority} | state={state_name} | labels={labels} | assignees={assignees} | start_date={start_date} | due_date={due_date} | estimate={estimate}
  ```
- Skip all `mcp__plane__create_work_item` calls.
- Print: `DRY_RUN complete — no items were created.`

If `DRY_RUN=false`:
- Process issues **sequentially** (not in parallel) to respect API rate limits
  and preserve a predictable order. This runs only after the preview gate is
  approved.

**Duplicate detection (per issue, before creating):**
- Call `mcp__plane__list_work_items` with `workspace_slug=PLANE_WORKSPACE_SLUG`,
  `project_id=PLANE_PROJECT_ID`, and filter/search by the issue title.
- Check if any existing item has a title that matches the current issue's title
  (case-insensitive exact match after stripping leading/trailing whitespace).
- If a duplicate is found:
  - Print: `WARN: Duplicate found for '{title}' (seq={existing_sequence_id}) — skipping.`
  - Increment the `N_skipped` counter.
  - Skip the `mcp__plane__create_work_item` call for this issue.
  - Continue to the next issue.

For each non-duplicate issue, call `mcp__plane__create_work_item` with:
  ```json
  {
    "workspace_slug": "{PLANE_WORKSPACE_SLUG}",
    "project_id": "{PLANE_PROJECT_ID}",
    "name": "{title}",
    "description_html": "<local-template or full_description rendered as HTML>",
    "priority": "{priority}",
    "state": "{state_id}",
    "label_ids": ["{label_id}", "..."],
    "assignee_ids": ["{member_id}", "..."],
    "start_date": "{start_date or null}",
    "target_date": "{due_date or null}",
    "estimate_point": "{estimate or null}"
  }
  ```
  > Note: if `description_html` is not accepted, send `description` as plain
  > markdown text while preserving the same local-template sections. Omit null
  > fields entirely rather than sending them as null.
- On success: store `{ sequence_id, id, name }` in `CREATED`.
- On error: log `ERROR [N/{total}] "{title}": {error message}` and continue
  (do not abort the batch).
- Print progress after each item: `[N/{total}] Created: "{title}" (seq={sequence_id})`.

---

## Step 5 — Print summary

After all items are processed, call `mcp__plane__retrieve_work_item` for each
created item to obtain the canonical URL (or construct it from `sequence_id` if
`url` is not returned by the create call).

Print the summary table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
issuer — Summary
Project  : {project.name}
Workspace: {PLANE_WORKSPACE_SLUG}
Backend  : plane
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
| # | Title                          | Priority | State       | URL |
|---|--------------------------------|----------|-------------|-----|
| 1 | {title}                        | {pri}    | {state}     | {url} |
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total created : {N_created}
Total skipped : {N_skipped}
Total errors  : {N_errors}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If `TASK_DIR` is set, also write the summary table to
`{TASK_DIR}/context/issue-publish-result.md`.

---

## Quirks (Plane API)

These behaviors are confirmed from production runs against the Plane MCP server
and are easy to mis-handle on first encounter. Read this section before adding
new mutating calls or debugging unexpected error messages.

### Q1. `mcp__plane__retrieve_work_item` Pydantic adapter validation bug

`mcp__plane__retrieve_work_item` occasionally surfaces a Pydantic-side
validation error whose message body **leaks the raw work-item fields** as
"unexpected" inputs. The leaked payload looks like a successful response with
the fields wrapped inside a `ValidationError` envelope. Treat this as a
known false-positive:

- Do NOT abort the workflow on this specific error shape — the underlying
  retrieve usually succeeded; only the post-fetch validation layer failed.
- Re-fetch the work item via `mcp__plane__retrieve_work_item_by_identifier`
  (project_identifier + issue_identifier) as the recovery path. That call uses
  a different validator and returns cleanly.
- Never paste the raw error body into user-visible output verbatim — it
  contains internal field shapes that aren't part of the public API.

### Q2. `description_html` truncation during bulk creation

When `mcp__plane__create_work_item` is called in rapid succession with large
`description_html` payloads (TipTap-rendered, with TaskList nodes and multiple
section headings), the server occasionally **stores only the first ~4-8 KB of
the HTML** and silently drops the tail. The create call returns success and
the item is created with a truncated body.

Workaround:

- For any issue whose `description_html` exceeds ~3 KB, perform the create
  with a minimal body (title + first section) and then immediately call
  `mcp__plane__update_work_item(work_item_id=<new id>, description_html=<full body>)`.
- The update path does NOT exhibit the truncation behavior.
- After every bulk-create batch, verify by retrieving the item and checking
  that the description length matches the source.

### Q3. TipTap TaskList HTML form (ENRTC-437 proven)

Plane's editor is TipTap-based. The body field accepts HTML, but task lists
must use the TipTap TaskList node form, not Markdown checkbox syntax. The
form that has been verified to render correctly (proven on ENRTC-437):

```html
<ul data-type="taskList">
  <li data-type="taskItem" data-checked="false">
    <label><input type="checkbox"><span></span></label>
    <div><p>Item text here</p></div>
  </li>
  <li data-type="taskItem" data-checked="true">
    <label><input type="checkbox" checked="checked"><span></span></label>
    <div><p>Completed item</p></div>
  </li>
</ul>
```

When producing checklists for `description_html`, emit this exact node shape.
Do not emit `<ul><li><input type="checkbox">...</li></ul>` — the editor
will render it as plain text, not as an interactive task item.

### Q4. Literal `[x]` is prohibited in `description_html`

Markdown-style checkbox literals (`- [ ]`, `- [x]`, `[X]`) MUST NOT appear in
the `description_html` payload. They are rendered verbatim as text rather than
as checkboxes (per the TipTap rule in Q3). This is a captured project-level
constraint (see mnemos `feedback-plane-checkbox-html`):

- Strip every `[ ]` / `[x]` literal from incoming markdown before composing
  the HTML body.
- Convert each stripped checkbox into a TaskList item using the Q3 node shape.
- If the source markdown is preserved elsewhere (e.g. in a comment or in
  `description_stripped` markdown form), the literal `[x]` is acceptable
  there — the prohibition applies only to the HTML body field.

---

## Lifecycle Management — State Transitions

The issuer-plane adapter supports work item lifecycle management beyond
creation. When the user requests a state change (e.g. "ENRTC-273 완료 처리",
"이슈 상태 변경", "작업 시작"), the adapter transitions the work item through
the project's configured states.

### Supported Operations

| Operation | User Intent Examples | Target State Group |
|---|---|---|
| Start work | "작업 시작", "진행중으로 변경", "start" | `started` (In Progress) |
| Complete | "완료", "done", "끝", "완료 처리" | `completed` (Done) |
| Block / Hold | "보류", "블록", "hold", "blocked" | fallback to project-specific state |
| Send to QA | "QA", "테스트 요청" | `started` (QA) |
| Deploy ready | "배포 대기", "deploy ready" | `started` (배포대기) |
| Cancel | "취소", "cancel" | `cancelled` (Cancelled) |
| Reopen | "다시 열기", "reopen", "백로그로" | `backlog` (Backlog) |

### Resolution Flow

1. **Identify the target work item.** Resolve by:
   - Project identifier + sequence number: `ENRTC-273` →
     `mcp__plane__retrieve_work_item_by_identifier(project_identifier="ENRTC", issue_identifier=273)`
   - Work item UUID (if already known from context)
   - Title search: `mcp__plane__search_work_items(query="...")`

2. **Resolve the target state.** Call `mcp__plane__list_states` and match
   by name (case-insensitive) or state group. Use the state group mapping:

   | State group | Project states (ENRTC) |
   |---|---|
   | `backlog` | Backlog |
   | `unstarted` | Todo |
   | `started` | In Progress, QA, 배포대기(Deploy Ready) |
   | `completed` | Done |
   | `cancelled` | Cancelled |

3. **Apply the transition.**
   ```
   mcp__plane__update_work_item(
     project_id=PLANE_PROJECT_ID,
     work_item_id=WORK_ITEM_ID,
     state=TARGET_STATE_ID
   )
   ```

4. **Report the result.**
   ```
   ✅ {IDENTIFIER}-{SEQ} "{title}" → {new_state_name}
   ```

### Bulk State Transitions

When multiple issues are specified (e.g. "ENRTC-273~280 완료 처리",
"목록 이슈 전부 In Progress로"), resolve each and apply transitions
in sequence. Print a summary table:

```
| # | Issue | Title | Before | After |
|---|---|---|---|---|
| 1 | ENRTC-273 | 본문 조회 | Backlog | Done |
| 2 | ENRTC-274 | Q&A 카테고리 | Backlog | Done |
...
Total: {N} issue(s) transitioned
```

### Additional Update Operations

The lifecycle management also supports updating other fields in a single call:

- **Labels**: "ENRTC-273에 에누리BE 라벨 추가"
- **Priority**: "ENRTC-273 우선순위 high로 변경"
- **Assignees**: "ENRTC-273 담당자 변경"

These use the same `mcp__plane__update_work_item` call with the relevant
field parameters.

### Partial Update Discipline (Plane PATCH semantics)

`mcp__plane__update_work_item` behaves as a partial PATCH: **only the fields
explicitly sent in the request body are modified.** Fields not included in the
call are left at their current server-side values. This makes targeted single-
field updates safe and is the recommended discipline for every lifecycle
operation.

**Always-safe omissions** (do NOT send them unless you intend to change them):

| Field | Why omitting is safe |
|---|---|
| `name` | Title rewrite is destructive to backlog readability; never overwrite unintentionally. |
| `description_html` / `description_stripped` | The body is the largest field and the most expensive to re-derive; omitting preserves the existing rendered body. |
| `label_ids` | Plane treats this as a **set replacement**, not a merge — sending `[]` clears every label. |
| `assignee_ids` | Same set-replacement semantics as `label_ids`. |
| `priority`, `state`, `start_date`, `target_date`, `estimate_point` | Each is independently updateable; omit unless the operation targets it. |

**Merge-vs-replace gotcha (`label_ids`, `assignee_ids`):**

For a "add label X" intent, the dispatcher MUST first read the current
`label_ids` (via `mcp__plane__retrieve_work_item` or
`retrieve_work_item_by_identifier`), append the new label id to the existing
list, then send the union. Sending `label_ids=[<new_id_only>]` will silently
drop every previously-attached label. The same rule applies to
`assignee_ids`.

**Single-field state transition (safe shape):**

```text
mcp__plane__update_work_item(
  workspace_slug=PLANE_WORKSPACE_SLUG,
  project_id=PLANE_PROJECT_ID,
  work_item_id=WORK_ITEM_ID,
  state=TARGET_STATE_ID
)
```

This call leaves title, description, labels, assignees, dates, estimate, and
priority untouched. It is the canonical shape for the lifecycle `transition`
operation.

**Verify-after-mutation rule:**

Every lifecycle update SHOULD be followed by a `retrieve_work_item_by_identifier`
read-back that confirms the targeted field reached the intended value. Bulk
operations may batch the verify reads at the end of the loop. If the read-back
disagrees with the intended value, surface the discrepancy in the result row
(STATUS=DRIFT) rather than reporting OK.

---

## Error Handling

- **PLANE_WORKSPACE_SLUG missing**: abort immediately with clear message.
- **Project not found**: abort immediately with a clear message listing available
  projects. Do not attempt any create calls.
- **Label creation failure**: log the error and omit that label from the affected
  issues. Continue processing remaining issues.
- **State not found**: fall back to the default unstarted state; log a warning
  per affected issue.
- **Assignee not found**: log a warning and omit that assignee. Continue processing.
- **Work item creation failure**: log the error and continue. Report the failing
  issue in the summary error count.
- **File not found / unreadable**: abort immediately with:
  `ERROR: Cannot read ISSUES_FILE "{ISSUES_FILE}". Check the path and try again.`
- **Authentication failure** (`mcp__plane__get_me` returns an error): abort with:
  `ERROR: Plane authentication failed. Verify PLANE_WORKSPACE_SLUG and MCP credentials.`

---

## Usage Examples

### Standard publish

```
User: publish the issues in docs/be-tasks-plane-issues.md to the "Backend" project

Inputs resolved:
  ISSUES_FILE          = docs/be-tasks-plane-issues.md
  BACKEND_ADAPTER      = plane           (default)
  PLANE_WORKSPACE_SLUG = my-org          (from env)
  PLANE_PROJECT_NAME   = Backend
  DRY_RUN              = false

Step 0: get_me -> "김태욱" — OK
        list_projects -> found "Backend" (id=abc123)
        TARGET_SUMMARY:
          backend: plane
          project_name: Backend
          project_id: abc123
          workspace_slug: my-org

[Dispatcher runs Step 0.5 — user approves]

Step 1: Parsed 12 issues
Step 2: Labels: [feature, bug, auth] — 2 existing, 1 created
Step 2b: Assignees: [dev@example.com] — 1 resolved
Step 3: States: Todo (id=s1), In Progress (id=s2), Done (id=s3)
Step 3.5: Preview 12 issues
        [A] Approve — proceed with publication
        [B] Cancel — stop, do not publish
        -> [A] Approve
Step 4: Creating 12 work items...
        Duplicate check [1/12] "Add login endpoint" — no duplicate
        [1/12] Created: "Add login endpoint" (seq=42)
        Duplicate check [2/12] "Fix JWT expiry bug" — no duplicate
        [2/12] Created: "Fix JWT expiry bug" (seq=43)
        ...
Step 5: Summary printed. Result written to TASK_DIR/context/issue-publish-result.md
```

### Dry-run example

```
User: dry-run publish docs/be-tasks-plane-issues.md to project id=abc123 workspace=my-org

  DRY_RUN=true
  Steps 0: Prerequisites and resolution run normally; TARGET_SUMMARY emitted
  Step 0.5: DRY_RUN bypass — confirmation prompt skipped (no mutations will occur)
  Steps 1-3: Field and ID resolution run normally
  Step 4:
    DRY_RUN [1/12] "Add login endpoint" | priority=high | state=Todo | labels=[] | ...
    ...
  DRY_RUN complete — no items were created.
```

### Interactive project selection example

```
User: publish issues from docs/tasks.md to workspace my-org (no project specified)

  PLANE_PROJECT_ID   = (absent)
  PLANE_PROJECT_NAME = (absent)
  -> calls list_projects, filters to member projects
  -> presents AskUserQuestion:
       "Which Plane project should issues be published to?"
       [A] Backend  (id=abc123)
       [B] Frontend (id=def456)
       [C] Infra    (id=ghi789)
  User selects [B] -> PLANE_PROJECT_ID=def456, PLANE_PROJECT_NAME=Frontend
  TARGET_SUMMARY:
    backend: plane
    project_name: Frontend
    project_id: def456
    workspace_slug: my-org
  -> Dispatcher runs Step 0.5 confirmation
  -> continues with Step 1
```
