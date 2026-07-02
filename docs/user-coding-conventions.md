# User Coding Conventions

Issue #191 adds a local user-convention channel for implementation agents.
The repository stores the mechanism only. The actual coding convention content
is not remote project state and may differ for every installed user.

## Storage Boundary

`memory convention` writes to a local cache:

```text
${AGENT_CREW_CONVENTION_CACHE_DIR:-${AGENT_CREW_HOME}/cache/user-conventions}/{owner}.json
```

The default owner is `AGENT_CREW_USER_ID`, then `$USER`, then `default`.
Use a different owner or cache directory when testing or when multiple local
profiles share the same machine.

## Commands

```bash
memory convention capture --content "Prefer pathlib.Path for new Python paths."
memory convention update <id> --content "Prefer pathlib.Path for new path work."
memory convention retire <id>
memory convention snapshot --task-dir "$TASK_DIR" --task "$TASK" --stage backend
memory convention show-cache
```

`capture`, `update`, and `retire` modify only the local per-user cache. They do
not require mnemos to be installed and do not sync convention content to the
remote repository.

## Runtime Loading

At task runtime the supervisor creates
`{TASK_DIR}/context/user-conventions.snapshot.json` once. Later stages reuse
that frozen task snapshot and receive only a digest path through
`USER_CONVENTIONS_PATH`.

The snapshot preserves the active owner/project convention set. Stage-specific
filters such as `--applies-to frontend` are applied when generating the
per-stage digest, not when freezing the task snapshot.

If a convention changes during an active task, the active task keeps using the
frozen snapshot unless an explicit refresh is requested:

```bash
memory convention snapshot --task-dir "$TASK_DIR" --task "$TASK" --stage backend --refresh
```

New tasks naturally see the latest local cache.

## Verification

Agents must apply relevant conventions while doing real work. Reviewer uses the
same digest as a review lens and can return `NEEDS_CHANGES` for concrete changed
line violations.

Do not create mandatory convention-use evidence files. Convention application is
validated through the normal evidence surface: diffs, focused tests, reviewer
findings, and tool events.
