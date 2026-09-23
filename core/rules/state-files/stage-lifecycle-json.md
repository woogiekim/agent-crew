# stage-lifecycle JSON — child invocation state

Each supervisor-owned child invocation writes one provider-neutral state file
under:

```text
{TASK_DIR}/context/stage-lifecycle/{lifecycle-id}.json
```

`core/scripts/stage_lifecycle.py` is the only decision source. Native
supervision and `HOST_BRIDGE: current_session_required` use the same helper;
host adapters only bind spawn, bounded wait, progress inspection, and
interrupt capabilities.

The artifact separates:

- `dispatched_at`
- `first_output_at`
- `artifact_ready_at`
- `terminal_at`
- `parent_resume_at`
- terminal state and reason
- `timed_out` and `interrupted`
- interval and total elapsed seconds

Artifact presence is not terminal success. A verified read-only result may use
the bounded terminal grace policy after subprocess and progress checks. A
mutating child with no terminal status is never restarted from scratch because
that can duplicate side effects; it is interrupted and blocked for explicit
recovery. A missing lifecycle file is valid legacy state and does not block
resume or repair.

Schema: `core/schemas/stage-lifecycle.schema.json`.
