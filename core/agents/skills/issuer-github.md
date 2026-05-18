# issuer-github — GitHub Backend Adapter

This skill implements the `issuer` agent's Adapter Interface Contract for the
**GitHub** issue tracker. It is loaded by the `issuer` dispatcher when
`BACKEND_ADAPTER=github`.

Uses the `gh` CLI for all API calls. The `gh` CLI handles authentication via
`gh auth login` and is the preferred path over raw `curl` / REST API calls
because it respects per-repo credential helpers and produces auditable output.

## Tools Required

| Tool | Purpose |
|---|---|
| `Bash` — `gh auth status` | Verify authentication |
| `Bash` — `gh repo view` | Confirm the target repository exists and is accessible |
| `Bash` — `gh label list` | Check which labels already exist |
| `Bash` — `gh label create` | Create missing labels before referencing them |
| `Bash` — `gh issue list` | Duplicate detection before creating each issue |
| `Bash` — `gh issue create` | Publish each parsed issue |
| `Bash` — `gh issue view` | Fetch the canonical URL for the summary table |

## Inputs (GitHub-specific)

In addition to the abstract inputs (`ISSUES_FILE`, `DRY_RUN`, `TASK_DIR`),
the GitHub adapter accepts:

- `GITHUB_REPO` (or `REPO`) — Repository in `owner/name` format.
  If omitted, the adapter resolves it from the current git remote (`origin`).
  Required when the working directory is not a GitHub-tracked git repository.

Input resolution priority for repository:
1. `GITHUB_REPO` input parameter
2. `REPO` input parameter
3. `gh repo view --json nameWithOwner -q .nameWithOwner` (current directory)
4. (error if none of the above)

---

## Step 0 — Authenticate and resolve repository

1. Run `gh auth status` to confirm the authenticated user. Print:
   `Authenticated as: {username} ({email or GitHub URL})`.
   If `gh` is not installed or not authenticated, abort with:
   ```
   ERROR: gh CLI is required but not found or not authenticated.
   Install gh: https://cli.github.com/
   Authenticate: gh auth login
   ```

2. Resolve `GITHUB_REPO`:
   - Use `GITHUB_REPO` if provided as input.
   - Otherwise use `REPO` if provided.
   - Otherwise run: `gh repo view --json nameWithOwner -q .nameWithOwner`
     in the current directory.
   - If still absent (not in a git repo or remote is not GitHub), abort with:
     `ERROR: GITHUB_REPO is required. Provide it as input (e.g. GITHUB_REPO=owner/repo) or run from within a GitHub-tracked git repository.`

3. Confirm the repository is accessible:
   ```bash
   gh repo view "${GITHUB_REPO}" --json name -q .name
   ```
   On error, abort with:
   `ERROR: Cannot access repository "${GITHUB_REPO}". Check the repo name and your gh auth permissions.`

---

## Step 1 — Parse the issues file

Read `ISSUES_FILE`. Each `##` heading starts a new issue.

Parse each issue block for the following fields:

| Field | Source | Notes |
|---|---|---|
| `title` | `##` heading text | Required |
| `body` | `### Description` section content | Optional; may be empty |
| `labels` | `**Labels:** ...` line | Comma-separated; optional |
| `assignees` | `**Assignees:** ...` line | Comma-separated GitHub usernames or emails; optional |
| `milestone` | `**Milestone:** ...` line | Milestone title; optional |

Fields are case-insensitive and the `**` bold markers are optional.

GitHub does not have native Priority or Estimate fields on issues. If the issues
file contains `**Priority:**` or `**Estimate:**` lines, add them as labels
(e.g. `priority:high`, `estimate:3`) so the data is not silently discarded.

---

## Step 2 — Resolve or create labels

1. Run `gh label list --repo "${GITHUB_REPO}" --limit 200` to fetch existing labels.
2. For each unique label in the parsed issues:
   - If the label already exists (case-insensitive match): use it as-is.
   - If the label does not exist and `DRY_RUN=false`: create it:
     ```bash
     gh label create "${label}" --repo "${GITHUB_REPO}" --color "ededed"
     ```
   - If `DRY_RUN=true`: note the label as would-be-created; do not create.
3. On label creation failure: log a warning and continue — do not abort the batch.

---

## Step 2b — Resolve assignee usernames

GitHub assignees must be valid GitHub usernames (not email addresses).

For each assignee string in the parsed issues:
- If the string matches `^[a-zA-Z0-9-]+$` (no `@`, no `.com`): use as a GitHub username directly.
- If the string is an email address: attempt to map to a GitHub username by running:
  ```bash
  gh api "search/users?q=${email}+in:email" --jq '.items[0].login' 2>/dev/null || echo ""
  ```
  If the mapping returns empty: log a warning ("Cannot resolve GitHub username for {email} — skipping assignee") and omit the assignee for that issue.
- Collect the final list of valid GitHub usernames for each issue.

---

## Step 3 — Resolve milestone IDs

GitHub's `gh issue create` accepts `--milestone` as a milestone title.

1. Run `gh api "repos/${GITHUB_REPO}/milestones" --jq '.[].title'` to list milestones.
2. For each issue's `milestone` field:
   - If the milestone exists: use the title directly in `--milestone`.
   - If it does not exist: log a warning and omit `--milestone` for that issue.

---

## Step 4 — Create issues

For each parsed issue, in order:

1. **Duplicate detection**: run:
   ```bash
   gh issue list --repo "${GITHUB_REPO}" --search "${title}" --state all \
     --json title -q '.[].title'
   ```
   If any result matches `title` (case-insensitive, exact): log
   `SKIP (duplicate): {title}` and move to the next issue.

2. If `DRY_RUN=true`: print the resolved payload (title, body, labels, assignees,
   milestone) and skip to the next issue without creating.

3. Create the issue:
   ```bash
   gh issue create \
     --repo "${GITHUB_REPO}" \
     --title "${title}" \
     --body "${body}" \
     [--label "${label}" ...] \
     [--assignee "${username}" ...] \
     [--milestone "${milestone}"]
   ```

4. Capture the issue URL from `gh issue create` output (printed to stdout as
   `https://github.com/{owner}/{repo}/issues/{N}`).

5. On creation failure: log the error and continue — do not abort the batch.
   Record the issue as `FAILED` in the summary.

---

## Step 5 — Print summary

Print a summary table after all issues are processed:

```
## GitHub Issue Creation Summary

Repository: {GITHUB_REPO}
Total: {total} | Created: {created} | Skipped (duplicate): {dupes} | Failed: {failed}

| # | Title | Labels | URL |
|---|---|---|---|
| 1 | {title} | {labels} | {url} |
| 2 | {title} | SKIPPED (duplicate) | — |
| 3 | {title} | FAILED | — |
```

If `TASK_DIR` is set, also write the summary to `{TASK_DIR}/context/issuer-github-summary.md`.

---

## Error Handling

- **`gh` not installed**: abort at Step 0 with install instructions.
- **`gh` not authenticated**: abort at Step 0 with `gh auth login` instruction.
- **Repository not accessible**: abort at Step 0 with the repo name and auth hint.
- **Label creation failure**: log warning, continue batch.
- **Issue creation failure**: log error, continue batch, mark as FAILED in summary.
- **Invalid assignee**: log warning, omit assignee, continue.
- **DRY_RUN=true**: no create calls are made; print all resolved payloads.
