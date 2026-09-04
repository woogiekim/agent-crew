# crew:variants — Candidate Variant Workflow

Manage candidate implementations created by `crew:run --variants N`.

```text
crew:variants collect
crew:variants select TASK_ID
crew:variants apply
```

`crew:variants collect` reads the active variants `session.json`, summarizes
completed candidate `result.md` files, writes `variant-summary.md`, keeps
`selection_status: "pending"`, and stops before any merge or branch mutation.

`crew:variants select TASK_ID` records the chosen candidate in `session.json`
with `selection_status: "selected"` and `selected_task_id`. It does not mutate
branches or apply the implementation.

`crew:variants apply` prints the approval-bound apply plan for the selected
candidate. It does not mutate branches by itself; applying the implementation
requires an explicit branch operation whose target, reversibility, and approval
contract are clear.

Use `crew:variants collect` for candidate collection.
