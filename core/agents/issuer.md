---
name: issuer
description: >
  TRIGGER when: user wants to publish issues or work items in bulk, create issues
  from a markdown file, import a task list into a project tracker, seed a project
  with pre-defined issues, upload an issue list to an issue tracking system,
  create multiple work items from a structured list, transition existing issue
  or work-item states, reopen/close/cancel/start/complete work items, or update
  non-state fields such as labels, priority, assignees, title, dates, estimate,
  or description.
  SKIP when: user only needs to read, query, or view existing work items without
  creating, transitioning, or updating them.
  Output: Work items created or updated via the selected backend adapter, with
  a summary table of issue titles, operations, states, fields, and URLs printed
  after completion.
reasoning_tier: balanced
model: inherit
---

# issuer — Issue Lifecycle Dispatcher

## Role

Manage issue and work-item lifecycle operations by dispatching to the
appropriate backend adapter skill. The dispatcher owns operation
classification, abstract interface contracts, input resolution, and the
dispatch-by-convention mechanism. All vendor-specific steps live in the
corresponding adapter skill.

The supported operations are:

- `create` — read a structured markdown file of issues and publish them as new
  work items.
- `transition` — resolve existing issue references and move their state.
- `update` — resolve existing issue references and update non-state fields.

Supported adapters (loaded by convention):
- `plane` → skill `issuer-plane` (installed at `~/.agent-crew/user/skills/issuer-plane.md`)
- `github` → skill `issuer-github` (installed at `~/.agent-crew/user/skills/issuer-github.md`)
- Future: `jira` → `issuer-jira`, `linear` → `issuer-linear`

To add a new adapter, create `~/.agent-crew/user/skills/issuer-{BACKEND_ADAPTER}.md`
following the Adapter Interface Contract below. No changes to this file are needed.

## Inputs

- `OPERATION_MODE` — Operation to run: `create`, `transition`, `update`, or
  `auto`. When omitted, infer it from the user's request using Operation
  Classification below. Default: `auto`.
- `ISSUES_FILE` — Path to the markdown file containing the issues to publish.
  Each issue is a `##` section (see Issue File Format below). **Required for
  `create`; unused for `transition` unless the adapter explicitly supports
  batch input from a file.**
- `ISSUE_REFS` — Existing issue or work-item references for `transition` and
  `update`. Accepts a single reference, a range, or a comma-separated list (see
  Issue References below). Required for `transition` and `update`.
- `TARGET_STATE` — Desired state name for `transition` operations, such as
  `Done`, `In Progress`, `Cancelled`, `QA`, `Deploy`, or any backend-specific
  state name configured in the target project.
- `FIELD_UPDATES` — Non-state fields to update for `update` operations:
  labels, priority, assignees, title, start date, due date, estimate,
  description, or backend-specific custom fields.
- `BACKEND_ADAPTER` — Which issue tracking backend to use. When omitted (or set to
  `"auto"`), the dispatcher auto-detects the correct adapter from `git remote get-url
  origin` (Step 0). Explicit values bypass auto-detection and load
  `issuer-{BACKEND_ADAPTER}` directly. Known values: `github`, `gitlab`, `plane`.
- `DRY_RUN` — Set to `true` to print all resolved work item payloads without
  making any create calls. Default: `false`.
- `TASK_DIR` — Task state directory (injected automatically by `crew:run`).

Backend-specific inputs (passed through to the adapter skill):

- `WORKSPACE_SLUG` — Workspace slug for the target backend (e.g. Plane workspace
  slug, Jira site name). Also accepted as `PLANE_WORKSPACE_SLUG` for backward
  compatibility. If absent, falls back to the `PLANE_WORKSPACE_SLUG` environment
  variable (Plane adapter only).
- `PROJECT_ID` — UUID or identifier of the target project. If omitted along with
  `PROJECT_NAME`, the adapter triggers interactive project selection.
- `PROJECT_NAME` — Human-readable project name used to resolve `PROJECT_ID`.
  If both `PROJECT_ID` and `PROJECT_NAME` are absent, interactive selection runs.

---

## Operation Classification

The dispatcher MUST classify the request before executing adapter work. When
`OPERATION_MODE` is provided and is not `auto`, use that value. Otherwise infer
the mode from the normalized user request.

| Operation | Trigger shape | Required inputs | Adapter branch |
|---|---|---|---|
| `create` | Publish/create/import/seed/upload issues from a file or structured list | `ISSUES_FILE` | Existing create flow: dispatcher Step 0 -> Step 0.5 -> Step 1 -> adapter Steps 1-5 |
| `transition` | Existing issue references plus state-change verbs such as complete, start, done, cancel, hold, QA, deploy, reopen, or Korean equivalents like 완료, 시작, 진행, 보류, 취소 | `ISSUE_REFS`, `TARGET_STATE` | Lifecycle flow: dispatcher Step 0 -> Step 0.5 -> adapter lifecycle state transition |
| `update` | Existing issue references plus non-state field changes such as label, priority, assignee, title, date, estimate, or description updates | `ISSUE_REFS`, `FIELD_UPDATES` | Lifecycle flow: dispatcher Step 0 -> Step 0.5 -> adapter lifecycle field update |

Classification rules:

1. If the request contains issue references and a state transition phrase,
   classify as `transition` even when the word "update" appears.
2. If the request contains issue references and non-state field changes,
   classify as `update`.
3. If the request has both state and field changes, split the work into a
   sequential lifecycle batch: apply `transition` and `update` per issue, then
   report each result row.
4. If classification is ambiguous, ask one structured choice before any
   mutation: `create`, `transition`, `update`, or cancel.
5. Read-only queries that only inspect existing issues are outside issuer's
   mutating lifecycle path and should route to a read-only agent instead.

---

## Issue References

Lifecycle operations resolve `ISSUE_REFS` into backend work-item IDs before any
state or field mutation. Adapters MUST support these formats:

| Input form | Example | Meaning |
|---|---|---|
| Single | `ENRTC-273` | One work item |
| Range | `ENRTC-273~280` | Inclusive sequence in the same project prefix |
| List | `ENRTC-273, ENRTC-275, ENRTC-280` | Explicit set of work items |

Resolution behavior:

- Preserve the project prefix from the first item in a range when the end of the
  range is numeric only.
- Resolve each reference to the backend's canonical work-item ID and URL before
  mutation.
- For bulk operations, process references sequentially and keep going after
  per-item failures unless the adapter loses authentication or target context.

---

## Issue File Format

The abstract issue format is tool-agnostic. Each `##` heading starts a new issue.
Recognised field lines follow the heading in any order:

```markdown
## Issue title here

**Priority:** urgent | high | medium | low | none
**State:** Todo | In Progress | Done | (any state name configured in the project)
**Labels:** label-one, label-two
**Assignees:** member@email.com, another@email.com
**StartDate:** YYYY-MM-DD
**DueDate:** YYYY-MM-DD
**Estimate:** 3

### Description

Free-form markdown description of the issue.

### Acceptance Criteria

- [ ] Criterion one
- [ ] Criterion two
```

- Fields are case-insensitive and the `**` bold markers are optional.
- All fields except the title are optional.
  Defaults: Priority=none, State=Todo, no labels, no assignees, no dates, no estimate.
- Issues without a `##` heading are skipped with a warning.
- The adapter maps these abstract fields to backend-specific API fields and IDs
  (e.g. state names are resolved to backend state IDs, label names to label IDs).

**Abstract field reference:**

| Field | Type | Notes |
|---|---|---|
| `Priority` | enum | `urgent` / `high` / `medium` / `low` / `none` |
| `State` | string | Any state name configured in the project |
| `Labels` | list | Comma-separated label names |
| `Assignees` | list | Comma-separated member emails or display names |
| `StartDate` | date | ISO format YYYY-MM-DD |
| `DueDate` | date | ISO format YYYY-MM-DD |
| `Estimate` | integer | Numeric point value |
| `Description` | markdown | Body of the `### Description` section |
| `Acceptance Criteria` | markdown | Body of the `### Acceptance Criteria` section |

---

## Workflow

### Step 0 — Tracker Resolution (auto-detect from git remote)

Before dispatching to any adapter, resolve which issue tracker backend to use by
inspecting the current repository's git remote. This step MUST run before
`BACKEND_ADAPTER` is consumed or defaulted.

**Algorithm:**

1. If `BACKEND_ADAPTER` is already explicitly set by the caller (non-empty, not the
   string `"auto"`), skip this step entirely and proceed to Step 0.5 (Dispatch).

2. Run the following command in `PROJECT_ROOT` (or the current working directory
   when `PROJECT_ROOT` is not set):

   ```bash
   git remote get-url origin 2>/dev/null
   ```

3. Match the remote URL against the following rules (in order):

   | Remote URL pattern | Action |
   |---|---|
   | Contains `github.com` | Set `BACKEND_ADAPTER=github`. Use `gh` CLI via the `issuer-github` user skill. |
   | Contains `gitlab.com` OR matches a self-hosted GitLab URL (heuristic: path contains `/gitlab/` or remote URL resolves to a GitLab instance) | Set `BACKEND_ADAPTER=gitlab`. Use `mcp__gitlab` tools. |
   | Empty / command failed (no remote configured) | Ask the user via the host's interactive question mechanism (see below). |
   | Any other URL (Bitbucket, Azure DevOps, etc.) | Present the detected remote to the user and ask for explicit consent before falling back to first-available adapter (see Fallback section below). |

4. **No remote — interactive resolution:**

   When `git remote get-url origin` returns nothing or exits non-zero, present
   the following prompt using `AskUserQuestion` (when the capability is available)
   or a plain-text question (fallback):

   - `header`: "No Git Remote Detected — Select Issue Tracker"
   - `question`: "No git remote origin was found in this repository. Which issue
     tracker should issues be published to?"
   - `options`:
     - `[A] GitHub — use gh CLI (issuer-github)`
     - `[B] GitLab — use mcp__gitlab (issuer-gitlab)`
     - `[C] Plane — use mcp__plane (issuer-plane)` _(default)_
     - `[D] Other — specify adapter name`

   Map the user's choice to `BACKEND_ADAPTER` (`github`, `gitlab`, `plane`, or the
   custom name entered for option D). Then proceed to Step 0.5.

5. **Unknown remote — explicit consent fallback:**

   When the remote URL does not match `github.com` or `gitlab.com`, display:

   ```
   [issuer] Unrecognized remote URL: {REMOTE_URL}
   No automatic adapter mapping available for this host.
   ```

   Then ask via `AskUserQuestion` (or plain-text fallback):
   - `header`: "Select Issue Tracker Adapter"
   - `question`: "Remote origin is '{REMOTE_URL}'. Which adapter should be used?"
   - `options`:
     - `[A] GitHub (gh CLI)`
     - `[B] GitLab (mcp__gitlab)`
     - `[C] Plane (mcp__plane)`
     - `[D] Other — specify adapter name`
     - `[E] Cancel`

   Do NOT automatically fall back to the first available adapter without this
   explicit consent step. If the user selects Cancel, halt with:
   ```
   STATUS: BLOCKED
   BLOCKER: user_cancelled_adapter_selection
   DETAIL: No adapter selected. Re-run and choose an adapter when prompted.
   ```

6. After Step 0 resolves `BACKEND_ADAPTER`, print a single line:

   ```
   [issuer] Resolved backend adapter: {BACKEND_ADAPTER} (source: {git_remote|explicit|interactive})
   ```

---

### Step 0.5 — Dispatch by adapter

1. Resolve `BACKEND_ADAPTER` from Step 0 above (already set; no default override).

2. Resolve `OPERATION_MODE` using Operation Classification above.

3. Load the skill named `issuer-{BACKEND_ADAPTER}`.
   The skill is installed at `~/.agent-crew/user/skills/issuer-{BACKEND_ADAPTER}.md`.
   This is a **convention-based load** — no registry lookup is needed.
   New adapters are auto-discoverable by placing the correctly-named skill file
   in `~/.agent-crew/user/skills/`.

4. If the skill file does not exist, return the following structured block
   and stop — do NOT attempt to call any external API, CLI, or service
   as a workaround:
   ```
   STATUS: BLOCKED
   BLOCKER: missing_adapter={BACKEND_ADAPTER}
   DETAIL: Adapter skill "issuer-{BACKEND_ADAPTER}" not found.
           Expected: ~/.agent-crew/user/skills/issuer-{BACKEND_ADAPTER}.md
           Supported adapters with installed skills: {list files matching issuer-*.md in user/skills/}
           To add a new adapter, create the skill file above following the
           Adapter Interface Contract in this file.
   ```
   The `STATUS: BLOCKED` return is machine-readable: the crew supervisor and
   any calling workflow will detect it and surface the blocker to the user
   without proceeding with direct API calls.

5. Execute the adapter skill's **Step 0** (authenticate and resolve target). The
   adapter Step 0 resolves all target coordinates (workspace slug, project ID,
   project name, repo, etc.) and returns them to the dispatcher as a structured
   `TARGET_SUMMARY:` block (see Adapter Interface Contract).

6. Execute **Step 1** (target confirmation) defined below.

7. Dispatch by operation:
   - `create`: Execute adapter Steps 1-5, passing through all inputs
     (`ISSUES_FILE`, `DRY_RUN`, `WORKSPACE_SLUG`, `PROJECT_ID`, `PROJECT_NAME`,
     `TASK_DIR`, and any backend-specific inputs the caller provided). The
     adapter must surface a preview gate before any create call when `DRY_RUN`
     is not enabled.
   - `transition`: Execute the adapter's lifecycle state-transition branch,
     passing `ISSUE_REFS`, `TARGET_STATE`, `DRY_RUN`, target coordinates, and
     any backend-specific inputs. The adapter must resolve references and show
     a pre-mutation preview unless `DRY_RUN=true`.
   - `update`: Execute the adapter's lifecycle field-update branch, passing
     `ISSUE_REFS`, `FIELD_UPDATES`, `DRY_RUN`, target coordinates, and any
     backend-specific inputs. The adapter must resolve references and show a
     pre-mutation preview unless `DRY_RUN=true`.

---

### Step 1 — Target Confirmation (pre-mutation gate)

**This step runs in the dispatcher (issuer.md) AFTER the adapter completes its
authentication step and BEFORE the adapter begins parsing (adapter Step 1).** It
surfaces the resolved target details to the user so they can catch wrong-org /
wrong-repo / wrong-workspace mistakes before any backend-mutating call fires.

#### Auto-confirm bypass

If the environment variable `AGENT_CREW_ISSUER_AUTO_CONFIRM=1` is set, skip the
interactive prompt entirely and log:

```
[issuer] Auto-confirm active (AGENT_CREW_ISSUER_AUTO_CONFIRM=1) — proceeding without prompt.
Target: {backend} | {project_name} ({project_id}) | workspace={workspace_slug} | operation={OPERATION_MODE} | file={ISSUES_FILE or N/A} | refs={ISSUE_REFS or N/A}
```

This bypass is intended for CI / batch contexts where no interactive terminal is
available. It MUST NOT silence the target summary line — the summary is always
printed even in auto-confirm mode.

#### DRY_RUN bypass

If `DRY_RUN=true`, skip the interactive confirmation prompt (no mutations will
occur) and print:

```
[issuer] DRY_RUN mode — skipping confirmation prompt (no mutations will occur).
Target: {backend} | {project_name} ({project_id}) | workspace={workspace_slug} | operation={OPERATION_MODE} | file={ISSUES_FILE or N/A} | refs={ISSUE_REFS or N/A}
```

#### Interactive confirmation

When neither bypass applies, present the confirmation block to the user.

**Build the confirmation block** from the adapter's Step 0 `TARGET_SUMMARY:` output:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
issuer — Target Confirmation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Backend       : {BACKEND_ADAPTER}
  Operation     : {OPERATION_MODE}
  Project       : {project_name} (id={project_id})
  Workspace/Org : {workspace_slug}   [omit line if N/A for this backend]
  Source file   : {ISSUES_FILE}       [create only; show N/A otherwise]
  Issue refs    : {ISSUE_REFS}        [transition/update only; show N/A otherwise]
  Issues to pub : {N} (parsed from {ISSUES_FILE}) [create only]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Show **resolved IDs verbatim** (not paraphrased) so the user can spot mistakes
at a glance.

**When `interactive_question` capability is available** (host supports
structured user-choice UI per `core/rules/capabilities/interactive-question.md`):

Use `AskUserQuestion` with:
- `header`: "Confirm Issue Publication Target"
- `question`: the confirmation block above (verbatim)
- `options`:
  - `[A] Approve — proceed with publication`
  - `[B] Cancel — stop, do not publish`

**When `interactive_question` capability is NOT available** (plain terminal
fallback):

Print the confirmation block and prompt:

```
Proceed with publication? [Y/N]:
```

#### Proceed / Abort logic

- If the user selects **Approve** or types **Y** (case-insensitive): continue to
  the selected adapter operation branch.
- Any other answer (Cancel, N, empty, or anything else): halt immediately with:
  ```
  STATUS: BLOCKED
  BLOCKER: user_cancelled_confirmation
  DETAIL: User declined to proceed. No issues were published.
          Re-run with correct target parameters and confirm when prompted.
  ```
  Do NOT call any backend-mutating API after a non-Y / non-Approve response.

#### Issue count resolution for the confirmation block

For `create`, the issue count `N` in the confirmation block is a **quick
pre-parse estimate**: count the number of `## ` heading lines in `ISSUES_FILE`.
This count is informational only (does not need to match the exact parsed count
from adapter Step 1 after field validation). If the file cannot be read at this
point, omit the count and show `Issues to pub: (unable to read file)`.

For `transition` and `update`, show `ISSUE_REFS` exactly as provided. The
adapter lifecycle branch owns full expansion and resolution after the target
confirmation gate.

---

## Adapter Interface Contract

Every adapter skill (`issuer-{BACKEND_ADAPTER}.md`) MUST implement the following
six-step interface plus a pre-publication preview gate. This contract is the
stable abstraction — the dispatcher and adapter skills both depend on it;
neither depends on the other.

| Step | Name | Responsibility |
|---|---|---|
| Step 0 | Authenticate and resolve project | Verify credentials; resolve or interactively select the target project; **emit a `TARGET_SUMMARY:` block for the dispatcher's Step 1** |
| Step 1 | Parse the issues file | Read `ISSUES_FILE`; extract titles, priorities, states, labels, assignees, dates, estimates, descriptions |
| Step 2 | Resolve or create labels | Map label names to backend IDs; create missing labels when allowed |
| Step 2b | Resolve assignee IDs | Map email/display-name values to backend member IDs |
| Step 3 | Resolve state IDs | Map state names to backend state IDs; fall back to default unstarted state |
| Step 3.5 | Preview resolved issues | Render a pre-create preview of the resolved issue set and require explicit approval before Step 4; bypassed in `DRY_RUN` |
| Step 4 | Create work items | For each issue: duplicate detection → (skip if duplicate) → create → log progress |
| Step 5 | Print summary | Print a summary table (seq#, title, priority, state, URL); write to TASK_DIR if set |

### Step 0 TARGET_SUMMARY block (required for Step 1)

At the end of Step 0, every adapter MUST emit a structured `TARGET_SUMMARY:` block
that the dispatcher uses to build the Step 1 confirmation screen. The block
format is:

```
TARGET_SUMMARY:
  backend: {BACKEND_ADAPTER}
  project_name: {resolved project name}
  project_id: {resolved project id / repo identifier}
  workspace_slug: {workspace or org slug, or "N/A" if not applicable}
```

The dispatcher reads these fields verbatim and uses them to build the confirmation
block in Step 1. Adapter Step 0 MUST NOT proceed to any mutating call before
emitting this block.

**Required behaviors in every adapter:**

- **Interactive project selection** — when `PROJECT_ID` and `PROJECT_NAME` are
  both absent, the adapter MUST present an interactive choice (via
  `AskUserQuestion`) listing available projects.
- **Pre-publication preview** — after Steps 1-3 complete and before any create
  call, the adapter MUST render a preview of the resolved issues and require
  explicit approval unless `DRY_RUN=true`.
- **Duplicate detection** — BEFORE each `create` call, the adapter MUST query
  existing items and skip any issue whose title already exists (case-insensitive).
- **DRY_RUN support** — when `DRY_RUN=true`, the adapter MUST print resolved
  payloads without making any create API calls, then print `DRY_RUN complete —
  no items were created.`
- **Graceful error handling** — label creation failures, state mismatches, and
  work item creation errors MUST be logged and skipped without aborting the batch.

### Lifecycle Management

Every adapter skill MUST also implement lifecycle branches for `transition` and
`update`. These branches reuse adapter Step 0 target resolution and the
dispatcher Step 1 target confirmation gate before any mutation.

| Capability | Responsibility |
|---|---|
| Issue resolution | Resolve `ISSUE_REFS` into canonical backend work-item IDs, titles, current states, and URLs. Support single references, ranges, and comma-separated lists. |
| State transition | Resolve `TARGET_STATE` to the backend state identifier, then update each resolved work item with that state. For backends that expose a generic update call, this is the abstract equivalent of `update_work_item(state=TARGET_STATE_ID)`. |
| Field update | Validate `FIELD_UPDATES`, resolve backend-specific IDs for labels, assignees, priority, dates, estimates, title, and description, then update each resolved work item. |
| Bulk operations | Process resolved references sequentially, continue after per-item validation or mutation failures, and preserve input order in the summary. |
| Result reporting | Print a per-item result table with reference, title, operation, previous value, new value, status, and URL. |

Lifecycle mutation gates:

- Before `transition` or `update`, render a preview that shows the resolved
  issue references, target state or field updates, and the exact target backend
  project/repository.
- Require explicit approval unless `DRY_RUN=true` or
  `AGENT_CREW_ISSUER_AUTO_CONFIRM=1`.
- If `DRY_RUN=true`, resolve references and payloads, print the would-change
  summary, and do not call a mutating backend API.
- If a reference cannot be resolved, mark that row as `FAILED` or `SKIPPED` and
  continue with remaining references.

Lifecycle result rows should be concise and auditable:

```text
OK     ENRTC-273 "Fetch article body" transition Todo -> Done https://...
FAILED ENRTC-274 "Unknown" transition unresolved_reference —
OK     ENRTC-275 "Parser cleanup" update labels += backend https://...
```

---

## Error Handling

- **User cancelled adapter selection at Step 0**: return `STATUS: BLOCKED` /
  `BLOCKER: user_cancelled_adapter_selection`. No adapter is loaded; no mutations occur.
- **Missing adapter skill**: return `STATUS: BLOCKED` / `BLOCKER: missing_adapter={adapter}` at Step 0.5. Never fall back to direct API calls.
- **File not found / unreadable**: abort immediately with:
  `ERROR: Cannot read ISSUES_FILE "{ISSUES_FILE}". Check the path and try again.`
- **User cancelled at Step 1**: return `STATUS: BLOCKED` / `BLOCKER: user_cancelled_confirmation`. No mutations have occurred.
- **Missing `ISSUE_REFS` for lifecycle operation**: return `STATUS: BLOCKED` /
  `BLOCKER: missing_issue_refs`. No mutations occur.
- **Unresolved issue reference**: record the row as `FAILED` or `SKIPPED` in the
  lifecycle summary and continue with remaining references.
- **Missing or invalid `TARGET_STATE` for `transition`**: return
  `STATUS: BLOCKED` / `BLOCKER: invalid_target_state` when no valid backend
  state can be resolved.
- **Missing or invalid `FIELD_UPDATES` for `update`**: return
  `STATUS: BLOCKED` / `BLOCKER: invalid_field_updates` when no valid field
  mutation remains after validation.
- **User cancelled lifecycle preview**: return `STATUS: BLOCKED` /
  `BLOCKER: user_cancelled_lifecycle_preview`. No mutations occur after
  cancellation.
- All other error scenarios are delegated to the adapter skill's own error handling.

---

## Usage Example

### GitHub remote (auto-detected)

```
User: publish the issues in docs/tasks.md to the "agent-crew" repo

Agent inputs resolved:
  ISSUES_FILE      = docs/tasks.md
  BACKEND_ADAPTER  = (not set — auto-detect)
  PROJECT_NAME     = agent-crew
  DRY_RUN          = false

Step 0:   $ git remote get-url origin
          → https://github.com/woogiekim/agent-crew.git
          Matched: github.com → BACKEND_ADAPTER=github
          [issuer] Resolved backend adapter: github (source: git_remote)

Step 0.5: Loading skill "issuer-github" from ~/.agent-crew/user/skills/issuer-github.md
          Executing GitHub adapter Step 0...
          Authenticated as: woogiekim (via gh CLI)
          Target repo: woogiekim/agent-crew
          TARGET_SUMMARY:
            backend: github
            project_name: agent-crew
            project_id: woogiekim/agent-crew
            workspace_slug: N/A

Step 1:   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          issuer — Target Confirmation
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Backend       : github
            Project       : agent-crew (id=woogiekim/agent-crew)
            Source file   : docs/tasks.md
            Issues to pub : 12
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          -> [A] Approve - proceed with publication
          -> [B] Cancel - stop, do not publish

          User selects [A] -> continue to adapter Step 1

Step 3.5: Preview 12 issues
          [A] Approve - proceed with publication
          [B] Cancel - stop, do not publish
          User selects [A] -> continue to Step 4

Adapter Steps 1-5: (adapter handles parsing, resolution, preview, creation, summary)
```

### Plane (explicit adapter, no auto-detect)

```
User: publish the issues in docs/tasks.md to the "Backend" project on Plane

Agent inputs resolved:
  ISSUES_FILE      = docs/tasks.md
  BACKEND_ADAPTER  = plane           (explicit — skips Step 0 auto-detect)
  PROJECT_NAME     = Backend
  DRY_RUN          = false

Step 0:   BACKEND_ADAPTER explicitly set — skipping git remote detection.
          [issuer] Resolved backend adapter: plane (source: explicit)

Step 0.5: Loading skill "issuer-plane" from ~/.agent-crew/user/skills/issuer-plane.md
          Executing Plane adapter Step 0...
          Authenticated as: 김태욱 (user@example.com)
          Target project: Backend (id=abc-123)
          TARGET_SUMMARY:
            backend: plane
            project_name: Backend
            project_id: abc-123
            workspace_slug: my-org

Step 1:   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          issuer — Target Confirmation
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Backend       : plane
            Project       : Backend (id=abc-123)
            Workspace/Org : my-org
            Source file   : docs/tasks.md
            Issues to pub : 12
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          -> [A] Approve - proceed with publication
          -> [B] Cancel - stop, do not publish

          User selects [A] -> continue to adapter Step 1

Step 3.5: Preview 12 issues
          [A] Approve - proceed with publication
          [B] Cancel - stop, do not publish
          User selects [A] -> continue to Step 4

Adapter Steps 1-5: (adapter handles parsing, resolution, preview, creation, summary)
```

### Lifecycle transition

```
User: ENRTC-273~280 진행중으로 변경

Agent inputs resolved:
  OPERATION_MODE   = transition
  ISSUE_REFS       = ENRTC-273~280
  TARGET_STATE     = In Progress
  BACKEND_ADAPTER  = (not set — auto-detect)
  DRY_RUN          = false

Step 0:   Resolve backend adapter and target project/repository.
Step 0.5: Load issuer-{BACKEND_ADAPTER}, run adapter Step 0, then dispatcher
          target confirmation.
Lifecycle branch:
          Resolve ENRTC-273 through ENRTC-280 to backend work-item IDs.
          Preview the state transition for each item.
          On approval, update each item sequentially.
          Print a result table with previous state, new state, status, and URL.
```

### Lifecycle field update

```
User: ENRTC-273, ENRTC-275 라벨 backend 추가하고 우선순위 high로 변경

Agent inputs resolved:
  OPERATION_MODE   = update
  ISSUE_REFS       = ENRTC-273, ENRTC-275
  FIELD_UPDATES    = labels += backend; priority = high
  BACKEND_ADAPTER  = (not set — auto-detect)
  DRY_RUN          = false

Lifecycle branch:
          Resolve each reference, validate labels and priority, preview the
          exact changes, apply approved updates sequentially, and print a
          per-item summary table.
```

See `~/.agent-crew/user/skills/issuer-plane.md` for the full Plane adapter
workflow, including workspace authentication, label resolution, state resolution,
duplicate detection, DRY_RUN mode, and the summary table format.
