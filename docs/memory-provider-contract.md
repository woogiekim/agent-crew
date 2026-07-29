# Memory Provider Contract

agent-crew depends on the `core/bin/memory` wrapper as its stable memory
provider boundary. Runtime agents and hooks must call this wrapper instead of
calling mnemos internals or reading mnemos storage files directly.

## Commands

The provider surface is:

| Command | Required | Behavior |
|---|---:|---|
| `memory capture` | yes | Stores support memory when a backend is available. Adds `--no-classify` by default for agent-crew support captures. |
| `memory search` | yes | Executes the configured recall mode. Legacy mode returns best-effort text results; V2 mode preserves provider JSON. |
| `memory read` | yes | Reads one memory item by id. Defaults to the local support backend unless `MNEMOS_BACKEND` is set. |
| `memory gc` | yes | Delegates garbage collection to the configured Mnemos provider. |
| `memory convention` | yes | Manages local per-installed-user coding convention cache and task snapshots without requiring mnemos. |
| `memory feedback` | no | Forwards provider feedback JSON only when `AGENT_CREW_MEMORY_FEEDBACK=1`. |

## Recall Modes

`AGENT_CREW_MEMORY_RECALL_MODE` controls `memory search`. The default is `v2`:

| Mode | Behavior |
|---|---|
| `off` | Skips recall and exits `0` with `status=disabled` on stderr. |
| `legacy` | Opt-in compatibility mode that delegates to provider `mnemos search` and preserves the text result contract. It does not read provider storage directly. |
| `shadow` | Diagnostic mode that runs Recall V2 read-only, discards its output for planning, then returns the provider legacy text result. |
| `v2` | Calls `mnemos recall --json` and preserves stdout JSON. It does not read mnemos SQLite/FTS internals, truncate result bodies, synthesize scores, or fall back to state-changing legacy search when recall is unavailable. |

`AGENT_CREW_MEMORY_STRICT=1` makes wrapper-level provider incompatibility,
timeout, invalid JSON, and unavailable states fail non-zero. The default
`AGENT_CREW_MEMORY_STRICT=0` reports the state and lets workflows continue
without memory. `AGENT_CREW_MEMORY_FEEDBACK=1` enables `memory feedback`;
the default `0` keeps feedback disabled.

## Local User Convention Surface

`memory convention` is part of the provider boundary because agents need a
stable entry point, but it is not a remote repository data source. The command
stores actual convention content in the installed user's local cache under
`${AGENT_CREW_CONVENTION_CACHE_DIR:-${AGENT_CREW_HOME}/cache/user-conventions}`.
Different users can have different conventions for the same project checkout.

Supported subcommands:

| Subcommand | Behavior |
|---|---|
| `capture` | Adds a local convention for the owner. |
| `update <id>` | Updates an existing local convention and bumps the cache version. |
| `retire <id>` | Marks a convention retired so future snapshots exclude it. |
| `snapshot` | Writes or reuses `{TASK_DIR}/context/user-conventions.snapshot.json` and emits a stage digest path. |
| `show-cache` | Prints the owner's local cache JSON. |

Task snapshots are frozen by default. If the local cache changes during an
active task, the active task sees the update only after an explicit
`memory convention snapshot --refresh`; new tasks use the latest cache.

## Recall V2 Contract

The default memory path requires `mnemos capabilities --json` to advertise JSON
recall and feedback support:

```json
{"commands":{"recall":{"json":true},"feedback":{"json":true}}}
```

Equivalent capability status fields such as `recall_v1=supported` and
`feedback_v1=supported` are accepted. The wrapper passes Recall V2 requests
through as JSON and preserves provider stdout JSON, including status values such
as `ok`, `no_results`, and `degraded`.

Required result fields from a structured Recall V2 backend are:

| Field | Required | Notes |
|---|---:|---|
| `id`, `item_id`, or `memory_id` | yes | Stable item identifier. |
| `content`, `text`, `preview`, or `snippet` | yes | Displayable text. |
| `retrieval_score`, `context_score` | no | Provider-owned scores. Agent Crew does not synthesize replacement relevance scores. |

Legacy human-readable search output remains available only when
`AGENT_CREW_MEMORY_RECALL_MODE=legacy` or `shadow` is explicitly selected.

## Failure Semantics

Wrapper-observable recall states are `disabled`, `ok`, `no_results`,
`degraded`, `unavailable`, `timeout`, `invalid_json`, and
`incompatible_provider`.

- Missing backend / no-backend mode: print a warning to stderr and exit `0`.
- Recall timeout: bounded wrapper emits `status=timeout` JSON for the default
  V2 path so the caller can proceed without memory.
- Capture timeout: warn and exit `0`; support-memory writes must not block a
  workflow.
- Partial capture failure after local id creation: warn, report the local id
  when detectable, and exit `0`.
- Non-sync capture errors: preserve the backend exit code.
- V2 incompatible provider: emit `status=incompatible_provider` JSON and do
  not fall back to legacy search.
- V2 timeout: emit `status=timeout` JSON and continue unless strict mode is
  enabled.
- V2 invalid provider JSON: emit `status=invalid_json` JSON and continue unless
  strict mode is enabled.

These rules keep agent-crew backend-agnostic while allowing mnemos to evolve its
storage path, FTS schema, metadata, and scoring model independently.
