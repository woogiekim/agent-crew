---
name: issuer
description: >
  TRIGGER when: user wants to publish issues or work items in bulk, create issues
  from a markdown file, import a task list into a project tracker, seed a project
  with pre-defined issues, upload an issue list to an issue tracking system, or
  create multiple work items from a structured list.
  SKIP when: user only needs to read, query, or view existing work items without
  creating new ones.
  Output: Work items created via the selected backend adapter, with a summary
  table of issue titles, priorities, states, and URLs printed after completion.
model: inherit
---

# issuer — Issue Publisher (Thin Dispatcher)

## Role

Read a structured markdown file of issues and publish them as work items by
dispatching to the appropriate backend adapter skill. The dispatcher owns the
abstract interface contract, input resolution, and the dispatch-by-convention
mechanism. All vendor-specific steps live in the corresponding adapter skill.

Supported adapters (loaded by convention):
- `plane` → skill `issuer-plane` (installed at `~/.agent-crew/user/skills/issuer-plane.md`)
- `github` → skill `issuer-github` (installed at `~/.agent-crew/user/skills/issuer-github.md`)
- Future: `jira` → `issuer-jira`, `linear` → `issuer-linear`

To add a new adapter, create `~/.agent-crew/user/skills/issuer-{BACKEND_ADAPTER}.md`
following the Adapter Interface Contract below. No changes to this file are needed.

## Inputs

- `ISSUES_FILE` — Path to the markdown file containing the issues to publish.
  Each issue is a `##` section (see Issue File Format below). **Required.**
- `BACKEND_ADAPTER` — Which issue tracking backend to use. Default: `plane`.
  The dispatcher loads the skill named `issuer-{BACKEND_ADAPTER}` automatically.
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

### Step 0 — Dispatch by adapter

1. Resolve `BACKEND_ADAPTER` (default: `plane`).

2. Load the skill named `issuer-{BACKEND_ADAPTER}`.
   The skill is installed at `~/.agent-crew/user/skills/issuer-{BACKEND_ADAPTER}.md`.
   This is a **convention-based load** — no registry lookup is needed.
   New adapters are auto-discoverable by placing the correctly-named skill file
   in `~/.agent-crew/user/skills/`.

3. If the skill file does not exist, return the following structured block
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

4. Execute the adapter skill's **Step 0** (authenticate and resolve target). The
   adapter Step 0 resolves all target coordinates (workspace slug, project ID,
   project name, repo, etc.) and returns them to the dispatcher as a structured
   `TARGET_SUMMARY:` block (see Adapter Interface Contract).

5. Execute **Step 0.5** (target confirmation) defined below.

6. Execute adapter Steps 1–5, passing through all inputs (ISSUES_FILE, DRY_RUN,
   WORKSPACE_SLUG, PROJECT_ID, PROJECT_NAME, TASK_DIR, and any backend-specific
   inputs the caller provided).

---

### Step 0.5 — Target Confirmation (pre-mutation gate)

**This step runs in the dispatcher (issuer.md) AFTER the adapter completes Step 0
and BEFORE the adapter begins Step 1 (parsing).** It surfaces the resolved target
details to the user so they can catch wrong-org / wrong-repo / wrong-workspace
mistakes before any backend-mutating call fires.

#### Auto-confirm bypass

If the environment variable `AGENT_CREW_ISSUER_AUTO_CONFIRM=1` is set, skip the
interactive prompt entirely and log:

```
[issuer] Auto-confirm active (AGENT_CREW_ISSUER_AUTO_CONFIRM=1) — proceeding without prompt.
Target: {backend} | {project_name} ({project_id}) | workspace={workspace_slug} | file={ISSUES_FILE}
```

This bypass is intended for CI / batch contexts where no interactive terminal is
available. It MUST NOT silence the target summary line — the summary is always
printed even in auto-confirm mode.

#### DRY_RUN bypass

If `DRY_RUN=true`, skip the interactive confirmation prompt (no mutations will
occur) and print:

```
[issuer] DRY_RUN mode — skipping confirmation prompt (no mutations will occur).
Target: {backend} | {project_name} ({project_id}) | workspace={workspace_slug} | file={ISSUES_FILE}
```

#### Interactive confirmation

When neither bypass applies, present the confirmation block to the user.

**Build the confirmation block** from the adapter's Step 0 `TARGET_SUMMARY:` output:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
issuer — Target Confirmation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Backend       : {BACKEND_ADAPTER}
  Project       : {project_name} (id={project_id})
  Workspace/Org : {workspace_slug}   [omit line if N/A for this backend]
  Source file   : {ISSUES_FILE}
  Issues to pub : {N} (parsed from {ISSUES_FILE})
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
  adapter Step 1.
- Any other answer (Cancel, N, empty, or anything else): halt immediately with:
  ```
  STATUS: BLOCKED
  BLOCKER: user_cancelled_confirmation
  DETAIL: User declined to proceed. No issues were published.
          Re-run with correct target parameters and confirm when prompted.
  ```
  Do NOT call any backend-mutating API after a non-Y / non-Approve response.

#### Issue count resolution for the confirmation block

The issue count `N` in the confirmation block is a **quick pre-parse estimate**:
count the number of `## ` heading lines in `ISSUES_FILE`. This count is
informational only (does not need to match the exact parsed count from Step 1
after field validation). If the file cannot be read at this point, omit the
count and show `Issues to pub: (unable to read file)`.

---

## Adapter Interface Contract

Every adapter skill (`issuer-{BACKEND_ADAPTER}.md`) MUST implement the following
six-step interface. This contract is the stable abstraction — the dispatcher and
adapter skills both depend on it; neither depends on the other.

| Step | Name | Responsibility |
|---|---|---|
| Step 0 | Authenticate and resolve project | Verify credentials; resolve or interactively select the target project; **emit a `TARGET_SUMMARY:` block for the dispatcher's Step 0.5** |
| Step 1 | Parse the issues file | Read `ISSUES_FILE`; extract titles, priorities, states, labels, assignees, dates, estimates, descriptions |
| Step 2 | Resolve or create labels | Map label names to backend IDs; create missing labels when allowed |
| Step 2b | Resolve assignee IDs | Map email/display-name values to backend member IDs |
| Step 3 | Resolve state IDs | Map state names to backend state IDs; fall back to default unstarted state |
| Step 4 | Create work items | For each issue: duplicate detection → (skip if duplicate) → create → log progress |
| Step 5 | Print summary | Print a summary table (seq#, title, priority, state, URL); write to TASK_DIR if set |

### Step 0 TARGET_SUMMARY block (required for Step 0.5)

At the end of Step 0, every adapter MUST emit a structured `TARGET_SUMMARY:` block
that the dispatcher uses to build the Step 0.5 confirmation screen. The block
format is:

```
TARGET_SUMMARY:
  backend: {BACKEND_ADAPTER}
  project_name: {resolved project name}
  project_id: {resolved project id / repo identifier}
  workspace_slug: {workspace or org slug, or "N/A" if not applicable}
```

The dispatcher reads these fields verbatim and uses them to build the confirmation
block in Step 0.5. Adapter Step 0 MUST NOT proceed to any mutating call before
emitting this block.

**Required behaviors in every adapter:**

- **Interactive project selection** — when `PROJECT_ID` and `PROJECT_NAME` are
  both absent, the adapter MUST present an interactive choice (via
  `AskUserQuestion`) listing available projects.
- **Duplicate detection** — BEFORE each `create` call, the adapter MUST query
  existing items and skip any issue whose title already exists (case-insensitive).
- **DRY_RUN support** — when `DRY_RUN=true`, the adapter MUST print resolved
  payloads without making any create API calls, then print `DRY_RUN complete —
  no items were created.`
- **Graceful error handling** — label creation failures, state mismatches, and
  work item creation errors MUST be logged and skipped without aborting the batch.

---

## Error Handling

- **Missing adapter skill**: return `STATUS: BLOCKED` / `BLOCKER: missing_adapter={adapter}` at Step 0. Never fall back to direct API calls.
- **File not found / unreadable**: abort immediately with:
  `ERROR: Cannot read ISSUES_FILE "{ISSUES_FILE}". Check the path and try again.`
- **User cancelled at Step 0.5**: return `STATUS: BLOCKED` / `BLOCKER: user_cancelled_confirmation`. No mutations have occurred.
- All other error scenarios are delegated to the adapter skill's own error handling.

---

## Usage Example

```
User: publish the issues in docs/tasks.md to the "Backend" project

Agent inputs resolved:
  ISSUES_FILE      = docs/tasks.md
  BACKEND_ADAPTER  = plane           (default)
  PROJECT_NAME     = Backend
  DRY_RUN          = false

Step 0:   Loading skill "issuer-plane" from ~/.agent-crew/user/skills/issuer-plane.md
          Executing Plane adapter Step 0...
          Authenticated as: 김태욱 (user@example.com)
          Target project: Backend (id=abc-123)
          TARGET_SUMMARY:
            backend: plane
            project_name: Backend
            project_id: abc-123
            workspace_slug: my-org

Step 0.5: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

          User selects [A] -> continue to Step 1

Steps 1-5: (adapter handles parsing, resolution, creation, summary)
```

See `~/.agent-crew/user/skills/issuer-plane.md` for the full Plane adapter
workflow, including workspace authentication, label resolution, state resolution,
duplicate detection, DRY_RUN mode, and the summary table format.
