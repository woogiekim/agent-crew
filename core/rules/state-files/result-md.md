# State File: result.md

`{TASK_DIR}/result.md` is the canonical terminal-state artifact written by the
supervisor at Phase 3 (close-out). The `crew:status` parser, `run.md` Step 7
Run Summary, and `crew:status --collect` all read this file.

Runtime guard evidence that is not a supervisor terminal close-out must not
overwrite `result.md`. For example, `supervisor-progress-guard.sh` writes
pipeline-bypass observer evidence to `result.violation.md` so completed
historical task results remain authoritative.

---

## Schema

Every `result.md` MUST begin with a Markdown h1 title line followed by a blank
line, then a block of **plain-text key: value fields** (no Markdown bold or
other formatting around the key name). Plain-text keys are required because the
`crew:status` parser uses simple `grep "^KEY:"` without any Markdown-aware
preprocessing.

### Required fields (all terminal states)

```
# {TASK DESCRIPTION}

STATUS: completed | blocked | CANCELLED
BRANCH: {branch name}
COMMITS: {integer}
```

### Additional fields for completed runs

```
DESCRIPTION: {TASK DESCRIPTION}
LOG:
{git log --oneline -5 output}

CHANGES:
  - {file path}: {one-line description of what changed}

DIFF_STAT:
{git diff $TASK_START_HEAD..HEAD --stat output}

DIFF_PREVIEW:
{git diff $TASK_START_HEAD..HEAD | head -200 output}
```

### Additional fields for blocked runs

```
BLOCKER: {machine-readable reason label}
DETAIL: {human-readable explanation, may wrap across multiple lines}
```

---

## Key rules

1. **Plain-text keys only.** Never use Markdown bold or other markup around a
   field key: `**STATUS:**` is forbidden. The correct form is `STATUS:`.
2. **Uppercase keys.** All required keys (`STATUS`, `BRANCH`, `COMMITS`, etc.)
   are uppercase.
3. **One key per line.** Each key appears at the start of its own line with no
   leading whitespace. Multi-line values (e.g. `LOG:`, `CHANGES:`, `DIFF_STAT:`,
   `DIFF_PREVIEW:`) are written as indented continuation lines.
4. **No trailing colon variations.** The separator is exactly `: ` (colon space).
   Do not use `= `, `— `, or plain `:` with no space.

---

## Canonical templates

### Completed run

```markdown
# {TASK}

DESCRIPTION: {TASK}
BRANCH: {BRANCH}
STATUS: completed
COMMITS: {N}
LOG:
{git log --oneline -5}

CHANGES:
  - {path}: {what changed}

DIFF_STAT:
{git diff $START_HEAD..HEAD --stat}

DIFF_PREVIEW:
{git diff $START_HEAD..HEAD | head -200}
```

### Blocked run

```markdown
# {TASK}

STATUS: blocked
BRANCH: {BRANCH}
BLOCKER: {reason}
DETAIL: {explanation}
```

### Cancelled at plan approval

```markdown
# {TASK}

DESCRIPTION: {TASK}
BRANCH: {BRANCH}
STATUS: CANCELLED
COMMITS: 0
LOG: (cancelled before execution)

CHANGES: none — cancelled at plan approval gate
```

---

## Parser compatibility note

The `crew:status` parser accepts **both** plain-text keys (canonical) and
Markdown-bold keys (`**STATUS:**`) for backward compatibility with runs
produced before this schema was formalized (GitHub issue #31).

Writers MUST use plain-text keys. The dual-format parser is a read-side
safety net — not a license to write non-canonical output.

---

## Writers

| Writer | Format output |
|---|---|
| `core/agents/supervisor-retry.md` Phase 3 | plain-text (canonical) |
| `core/agents/supervisor-bootstrap.md` Phase 1d (CANCELLED) | plain-text (canonical) |
| `core/agents/supervisor-bootstrap.md` Phase 0 (state-schema error) | plain-text (canonical) |
| `core/agents/supervisor-bootstrap.md` Phase 0 (not-a-git-repo) | plain-text (canonical) |
| `core/agents/supervisor-retry.md` (stage_timeout) | plain-text (canonical) |
| `core/agents/supervisor-retry.md` (cost_budget_exceeded) | plain-text (canonical) |

All writers MUST follow the canonical plain-text format defined in this spec.
