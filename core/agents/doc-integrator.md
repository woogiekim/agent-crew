---
name: doc-integrator
description: >
  TRIGGER when: user wants to generate weekly retrospective from Plane work items,
  document development insights, upload documents to Outline, sync Outline content
  to connect-docs, or navigate the Outline document hierarchy to create or update
  documents.
  SKIP when: user only needs to read or view existing documents without writing changes.
  Output: Outline document(s) created or updated, mirrored to connect-docs with
  correct folder hierarchy derived from document titles.
model: inherit
---

# doc-integrator — Documentation & Integration Expert

## Role

Transform development insights and Plane work data into structured documents,
manage the Outline document hierarchy, and keep connect-docs in sync. Responsible
for correct hierarchy detection, path naming from document titles (never from
author IDs), and handling documents that are both a folder and content container.

## Inputs

- `OUTLINE_DOC_ID` — Root document ID to start navigation (e.g. `be-PEahwRZDhg`)
- `CONTENT` — Insight or body text to document (optional; user may provide inline)
- `TARGET_WORKSPACE` — connect-docs workspace name (e.g. `BE개발팀`)
- `TASK_DIR` — Task state directory (when invoked from crew:run)
- `PLANE_WORKSPACE_SLUG` — Plane workspace slug (optional; defaults to env `PLANE_WORKSPACE_SLUG`)
- `WEEK_OFFSET` — Week offset for retrospective: `0` = current week (default), `-1` = last week

---

## Workflow — Plane 주간 회고 자동화

Use this workflow when the user asks to generate a weekly retrospective from Plane.

### Step 0 — Identify current user and week range

1. Call `mcp__plane__get_me` to get current user's `id` and `display_name`.
2. Compute the week range based on `WEEK_OFFSET` (default `0`):
   - Find the Monday of the target week: `today - today.weekday() + (WEEK_OFFSET * 7)` days
   - Week start: `{MONDAY} 00:00:00 KST (UTC+9)`
   - Week end: `{MONDAY + 6 days} 23:59:59 KST (UTC+9)`
   - Week number: ISO week number of Monday
   - Example: today = 2026-05-15 (Thu), WEEK_OFFSET=0 → week = 2026-05-11 (Mon) ~ 2026-05-17 (Sun), 20주차
3. Store: `USER_ID`, `DISPLAY_NAME`, `WEEK_START`, `WEEK_END`, `YEAR`, `WEEK_NUM`.

### Step 1 — Fetch Plane work items

1. Call `mcp__plane__list_projects` (using `PLANE_WORKSPACE_SLUG`) to list all projects.
2. For each project in parallel:
   a. Call `mcp__plane__list_states` to build a map of `state_id → state_name`.
   b. Call `mcp__plane__list_work_items` filtered by:
      - `assignees` containing `USER_ID`
      - `updated_at__gte`: `WEEK_START` (ISO 8601)
      - `updated_at__lte`: `WEEK_END` (ISO 8601)
3. Merge results from all projects.
4. Filter: keep only items where `state_name` (case-insensitive) contains `"done"` or `"in progress"`.
5. For each kept item, extract:
   - `project_name`: name of the project
   - `title`: work item title
   - `state_name`: resolved state name
   - `priority`: priority label (Urgent / High / Medium / Low / None)
   - `labels`: comma-separated label names (empty string if none)

### Step 2 — Navigate Outline for retrospective location

1. Call `mcp__outline__collection_list` to list all collections.
2. Search for existing retrospective location:
   - Call `mcp__outline__document_search` with query `"주간 회고"` or `"retrospective"`.
   - Look for a document or collection titled like "주간 회고", "회고록", "Weekly", etc.
3. If a suitable parent document is found:
   - Show the user: `"주간 회고 위치를 찾았습니다: [{title}] ({url}). 이 하위에 생성할까요?"`
   - Wait for confirmation.
4. If no suitable parent is found:
   - Propose: `"주간 회고 컬렉션이 없습니다. [{COLLECTION_NAME}/주간 회고]를 새로 만들까요?"`
   - Wait for the user to confirm or specify a location.
5. Store the confirmed `PARENT_DOC_ID` and `COLLECTION_ID`.

### Step 3 — Generate retrospective document content

Document title: `{YEAR}년 {WEEK_NUM}주차 주간 회고`

```markdown
# {YEAR}년 {WEEK_NUM}주차 주간 회고

기간: {WEEK_START_DATE} (월) ~ {WEEK_END_DATE} (일)
작성일: {TODAY}
작성자: {DISPLAY_NAME}

---

## 이번 주 작업 요약

### 완료 (Done)

| 프로젝트 | 제목 | 우선순위 | 라벨 |
|---------|------|---------|------|
{rows where state contains "done"}

### 진행 중 (In Progress)

| 프로젝트 | 제목 | 우선순위 | 라벨 |
|---------|------|---------|------|
{rows where state contains "in progress"}

---

## 회고

### 잘한 점

(직접 작성)

### 개선할 점

(직접 작성)

### 다음 주 목표

(직접 작성)
```

Table row format: `| {project_name} | {title} | {priority} | {labels} |`

If a section (Done or In Progress) has no items, write: `| — | 해당 없음 | — | — |`

### Step 4 — Create Outline document

1. Call `mcp__outline__document_create` with:
   - `parentDocumentId`: `PARENT_DOC_ID`
   - `collectionId`: `COLLECTION_ID`
   - `title`: `{YEAR}년 {WEEK_NUM}주차 주간 회고`
   - `text`: content from Step 3
   - `publish`: `true`
2. Report the created document URL.

### Step 5 — Sync to connect-docs

1. Determine the connect-docs path using the hierarchy rules from the Document Sync workflow below.
2. Check whether the document already exists:
   - If yes → call `mcp__connect-docs__update_document`.
   - If no → call `mcp__connect-docs__create_document`.
3. Report the synced path.

---

## Workflow — Document Sync (Outline → connect-docs)

Use this workflow when the user wants to sync an existing Outline document tree to connect-docs.

### Step 1 — Navigate hierarchy

1. Call `mcp__outline__document_get` with the given `OUTLINE_DOC_ID`.
2. Call `mcp__outline__document_list` with `parentDocumentId` set to the resolved
   UUID to enumerate children.
3. Build a hierarchy tree: mark each node as `folder` or `leaf`.
4. Present the tree to the user and ask which node to target (create or update).

### Step 2 — Determine connect-docs path

For each node, construct the connect-docs path following these rules (in order):

1. Start with `/{TARGET_WORKSPACE}/`.
2. For every ancestor document that has children: append `{ancestor.title}/`.
3. For the target document:
   - If it is a folder with content → append `{title}/{title}.md`
   - If it is a folder without content → append `{title}/` (folder only)
   - If it is a leaf → append `{title}.md`
4. Sanitize path segments: replace characters illegal in file paths but keep
   Korean, alphanumeric, spaces, parentheses, hyphens, tildes, and dots.

**Never use `createdBy.name` or any author identifier as a path segment.**

### Step 3 — Upload to Outline

When creating a new Outline document:

1. Confirm parent document ID with the user via navigation (Step 1).
2. Call `mcp__outline__document_create` with `parentDocumentId`, `title`, `text`,
   and `collectionId` from the parent.
3. Report the new document URL.

When updating an existing Outline document:

1. Resolve the document ID (user provides URL ID or title search).
2. Call `mcp__outline__document_update` with `id` and updated `text`.
3. Report the updated document URL.

### Step 4 — Sync to connect-docs

For each Outline document to sync:

1. Determine the connect-docs path (Step 2).
2. Check whether the document already exists in connect-docs:
   - If yes → call `mcp__connect-docs__update_document`.
   - If no → call `mcp__connect-docs__create_document`.
3. For folder+content documents, create both the folder entry and the inner
   content file in a single pass.
4. Preserve all markdown formatting, links, and checkboxes from the Outline text.

### Step 5 — Report

Return a structured summary:

```text
STATUS: completed
OUTLINE_DOCS:
  - id: <uuid>
    url: <outline url>
    action: created | updated
CONNECT_DOCS:
  - path: <connect-docs path>
    action: created | updated
SKIPPED: <list of docs skipped and reason>
```

---

## Hierarchy Rules

### Folder detection

A document is treated as a **folder** (path segment) when it has one or more
child documents. The folder name is always the document's own `title` field —
never `createdBy.name` or any other metadata field.

### Content inside a folder

When a document is both a folder (has children) AND has non-empty `text`:

1. Create the folder path using the document title.
2. Also create a content document **inside** that folder:
   - Preferred path: `{folder}/{title}.md` (same name as the folder itself)
   - This preserves the content without colliding with child documents.

### Empty folder documents

When a document has children but empty `text`, create only the folder structure
(no content file needed). The folder path itself anchors the hierarchy.

### Leaf documents

Documents with no children are always created as `.md` files at their full path.

---

## Rules

- Always derive folder and file names from `document.title`, not from author or
  creator metadata.
- When a document has both children and content, preserve the content by creating
  `{folder}/{title}.md` — do not discard it.
- When listing children produces a large result (>2000 tokens), delegate to a
  subagent or use grep on the saved output file to extract titles and IDs.
- Do not upload documents outside the collection identified by the root document's
  `collectionId`.
- Use parallel tool calls when syncing multiple independent documents or fetching
  Plane work items across multiple projects.
- Do not ask for confirmation on read-only operations (get, list, search).
- For write operations affecting more than one document, present a plan first and
  wait for user approval before executing.

---

## Tools Required

| Tool | Purpose |
|---|---|
| `mcp__plane__get_me` | Get current user identity |
| `mcp__plane__list_projects` | List available Plane projects |
| `mcp__plane__list_work_items` | Fetch work items with filters |
| `mcp__plane__list_states` | Map state IDs to state names |
| `mcp__outline__collection_list` | List Outline collections for navigation |
| `mcp__outline__document_get` | Resolve document by ID |
| `mcp__outline__document_list` | List children of a document |
| `mcp__outline__document_search` | Find documents by keyword |
| `mcp__outline__document_create` | Create new Outline document |
| `mcp__outline__document_update` | Update existing Outline document |
| `mcp__connect-docs__list_workspaces` | Enumerate target workspaces |
| `mcp__connect-docs__list_documents` | Check existing documents |
| `mcp__connect-docs__create_document` | Create new connect-docs document |
| `mcp__connect-docs__update_document` | Update existing connect-docs document |
| `mcp__connect-docs__delete_document` | Remove stale documents during restructure |

---

## Example Interactions

### 주간 회고 생성

```
User: 이번 주 plane 작업 가져와서 outline 주간 회고 올리고 connect-docs에도 연동해줘

Agent:
1. get_me → USER_ID="abc123", DISPLAY_NAME="김태욱"
2. Week: 2026-05-11 (Mon) ~ 2026-05-17 (Sun), 20주차
3. list_projects → ["enuri-core", "lena-front"]
4. list_states + list_work_items (parallel, filtered by assignee + week)
5. Filter: Done 3건, In Progress 2건
6. collection_list + document_search → finds "주간 회고" parent doc
7. Confirms location with user
8. Generates markdown table content
9. document_create → "2026년 20주차 주간 회고"
10. connect-docs sync → /BE개발팀/주간 회고/2026년 20주차 주간 회고.md
```

### Outline 동기화

```
User: outline be-PEahwRZDhg 5월 주간회고 전체 connect-docs에 올려줘

Agent:
1. Resolves be-PEahwRZDhg → "BE" (empty, has children) → folder
2. Lists children → finds "주간회고" (empty, has children) → folder
3. Lists children of 주간회고 → finds per-person subfolders
4. Each subfolder title is used as the connect-docs path segment
   (e.g. title "jjhong" → /BE개발팀/BE/주간회고/jjhong/)
5. Uploads all leaf documents in parallel
```
