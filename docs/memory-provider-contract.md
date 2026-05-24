# Memory Provider Contract

agent-crew depends on the `core/bin/memory` wrapper as its stable memory
provider boundary. Runtime agents and hooks must call this wrapper instead of
calling mnemos internals or reading mnemos storage files directly.

## Commands

The provider surface is:

| Command | Required | Behavior |
|---|---:|---|
| `memory capture` | yes | Stores support memory when a backend is available. Adds `--no-classify` by default for agent-crew support captures. |
| `memory search` | yes | Returns best-effort text results. Uses stable fast JSON search when the backend advertises it. |
| `memory read` | yes | Reads one memory item by id. Defaults to the local support backend unless `MNEMOS_BACKEND` is set. |
| `memory gc` | yes | Runs agent-crew's local memory garbage-collection helper. |

## Search Output

Human-readable search output remains line-oriented for agent prompts:

```text
  [mnemos-fast score=0.91] memory-id: preview text
[mnemos] Retrieved 1 memories
```

Required result fields from a structured backend are:

| Field | Required | Notes |
|---|---:|---|
| `id`, `item_id`, or `memory_id` | yes | Stable item identifier. |
| `content`, `text`, `preview`, or `snippet` | yes | Displayable text. |
| `score` | no | Optional `0..1` relevance score. Omitted when unsupported. |

Backends may return either a JSON list or a JSON object with `results` or
`items`. agent-crew ignores unknown fields.

## Fast Search Capability

The preferred mnemos capability is:

```bash
mnemos capabilities --json
mnemos search --fast --json --limit 5 "query"
```

`capabilities --json` must advertise fast JSON search with one of:

```json
{"commands":{"search":{"fast":true,"json":true}}}
```

or an equivalent `search_fast` / `fast_search` boolean in the top-level object
or `features` object.

The deprecated compatibility fallback can still read the legacy local FTS
database when `AGENT_CREW_MEMORY_LEGACY_FTS_FALLBACK=1`, but this is not part of
the contract and may be removed after supported mnemos versions provide stable
fast JSON search.

## Failure Semantics

- Missing backend / no-backend mode: print a warning to stderr and exit `0`.
- Search timeout: bounded wrapper returns the timeout status for search so the
  caller can decide whether to proceed without recall.
- Capture timeout: warn and exit `0`; support-memory writes must not block a
  workflow.
- Partial capture failure after local id creation: warn, report the local id
  when detectable, and exit `0`.
- Non-sync capture errors: preserve the backend exit code.
- Invalid fast-search JSON: fall back to the next available search path.

These rules keep agent-crew backend-agnostic while allowing mnemos to evolve its
storage path, FTS schema, metadata, and scoring model independently.
