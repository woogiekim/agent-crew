# capabilities.json — Host Capability Advertisement

Host adapter capability flags. Lives at
`${STATE_DIR}/capabilities.json`. Written by the host adapter's
`setup.sh`; read by core code at runtime via the absence-tolerant
loader documented in `core/rules/host-capabilities.md`.

This doc is the **state-file schema** view of `capabilities.json`. The
**capability contract** (what each flag means, who consumes it, the
absence contract, the three invariants) lives in
`core/rules/host-capabilities.md`. F4 introduces this sibling doc only
to keep the state-files/ directory symmetric with the four other JSON
state files.

## File Location

```
${STATE_DIR}/capabilities.json
```

Where `STATE_DIR = ${AGENT_CREW_HOME}/state/${PROJECT_NAME}`. Wiped
by `crew:setup` reset (a fresh setup re-creates it from the active
adapter's `setup.sh`); preserved across `crew:update`.

## Schema

Canonical shape (Phase 3.5 flag set):

```json
{
  "schema_version":       1,
  "host":                 "claude",
  "task_tools":           true,
  "agent_background":     true,
  "monitor_tool":         true,
  "cost_tracking":        true,
  "hook_system":          true,
  "interactive_question": false,
  "interactive_question_mode": "codex_plan_mode_conditional",
  "interactive_question_surface": "request_user_input",
  "interactive_question_fallback": "structured_markdown"
}
```

JSON Schema: `${AGENT_CREW_HOME}/schemas/capabilities.schema.json`. The
schema sets `additionalProperties: true` because every refactor phase
that adds a capability adds a new flag here; the schema must not
require an exhaustive enumeration.

### Field catalog

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | integer (const 1) | optional | Pre-F4 adapters omit this; validator tolerates absence. |
| `host` | string | yes | Adapter name. Informational for capability gating; host bridge discovery may use it only as a legacy fallback after explicit command/env and active host process markers. |
| `task_tools` | boolean | optional (defaults false per absence contract) | Host task lifecycle tools. |
| `agent_background` | boolean | optional | Background subagent fan-out. |
| `monitor_tool` | boolean | optional | Streaming output surface. |
| `cost_tracking` | boolean | optional | Per-task token usage reporting. |
| `hook_system` | boolean | optional | Host enforces validators at lifecycle moments. Phase G6: true on Claude. |
| `interactive_question` | boolean | optional (planned) | Structured user-choice prompts. |
| `interactive_question_mode` | string | optional | Adapter-specific mode detail, e.g. `codex_plan_mode_conditional`. |
| `interactive_question_surface` | string | optional | Adapter-specific native surface, e.g. `request_user_input`. |
| `interactive_question_fallback` | string | optional | Fallback renderer, e.g. `structured_markdown`. |

Note: `reasoning_tier` is **install-time** (see
`host-capabilities.md` Capability Registry table); it does NOT appear
in `capabilities.json`.

## Lifecycle

### Created / Updated

Each host adapter's `setup.sh` overwrites this file on every
`crew:setup` invocation. Adapters that have no advertised surfaces
(`generic`) MAY skip writing the file entirely — the absence contract
ensures consumers still work.

### Read

Once per process at Phase 0 of the supervisor (via the single
`python3` block in `supervisor-bootstrap.md` that emits all four flags
in one call). `crew:status` reads it once in Step 1b. Other consumers
follow the same one-read-per-process pattern.

## Concurrency

Single-writer / many-reader. The adapter `setup.sh` is the only
writer and runs interactively (not from inside a supervisor). Readers
are tolerant of mid-write states because the absence-or-parse-error
contract treats malformed JSON as all-false flags — never as a hard
error.

## Consumer Contract

The full consumer contract is in `core/rules/host-capabilities.md` §
Consumer Contract. Summary:

| Situation | Behavior |
|---|---|
| File absent | Every flag = false (absence contract). |
| File present, parse error | Every flag = false. |
| File present, schema valid | Use the advertised values. |
| File present, unknown field | Forward-compat: ignore. |
| File present, `schema_version > 1` | Forward-compat: warn but continue. |

The F4 schema validator is the only consumer that distinguishes parse
errors from absence — and even there, the validator emits a **warning,
not an error** (this is a soft-warn class file per the F4 mixed
validator semantics). Hard halts on capabilities.json would contradict
the absence contract.

## Forward Compatibility

`additionalProperties: true`. New flags introduced by future phases
flow through automatically. Each addition is paired with:

1. A per-flag detail doc under `core/rules/capabilities/`.
2. An entry in `core/rules/host-capabilities.md` Capability Registry.
3. (Optional) An entry in this doc's field catalog.

The validator does not enforce that adapters write every advertised
flag — adapters set a flag to true only when the host genuinely
exposes it.

## Related Files

Producer:

- Each adapter's `setup.sh`:
  - `adapters/claude/setup.sh`
  - `adapters/codex/setup.sh` (may skip writing)
  - `adapters/generic/setup.sh` (may skip writing)

Consumers:

- `core/agents/supervisor-bootstrap.md` Phase 0 (4-flag bulk read)
- `core/commands/status.md` Step 1b (3-flag bulk read)
- `core/commands/cost.md` (cost-aggregate gating)
- `core/scripts/validate-state-schema.py` (Phase F4 schema validator — soft-warn class)

Sibling state-file docs:

- `core/rules/state-files/register-json.md`
- `core/rules/state-files/pipeline-json.md`
- `core/rules/state-files/session-json.md`
- `core/rules/state-files/progress-buffer-jsonl.md`

Schema:

- `core/schemas/capabilities.schema.json`

Authoritative cross-reference:

- `core/rules/host-capabilities.md` (capability contract, registry,
  absence contract, three invariants)
- `core/rules/capabilities/*.md` (per-flag detail)
