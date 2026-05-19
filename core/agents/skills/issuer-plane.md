# issuer-plane — Plane Backend Adapter

This skill implements the `issuer` agent's Adapter Interface Contract for the
**Plane** project management backend. It is loaded by the `issuer` dispatcher when
`BACKEND_ADAPTER=plane` (the default).

All six interface steps (Step 0 through Step 5) are defined below.

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
| `mcp__plane__retrieve_work_item` | Fetch canonical URL for the summary table |

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
   - `full_description`: concatenation of `description` and (if non-empty)
     a `## Acceptance Criteria` section appended from `acceptance_criteria`.

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
  and preserve a predictable order.

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
    "description_html": "<p>{full_description rendered as HTML}</p>",
    "priority": "{priority}",
    "state": "{state_id}",
    "label_ids": ["{label_id}", "..."],
    "assignee_ids": ["{member_id}", "..."],
    "start_date": "{start_date or null}",
    "target_date": "{due_date or null}",
    "estimate_point": "{estimate or null}"
  }
  ```
  > Note: if `description_html` is not accepted, fall back to sending
  > `description` as plain markdown text. Omit null fields entirely rather
  > than sending them as null.
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
