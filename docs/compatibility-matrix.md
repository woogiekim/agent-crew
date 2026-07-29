# agent-crew / mnemos Compatibility Matrix

This matrix documents the supported memory-provider boundary between
agent-crew and mnemos. The stable contract is `core/bin/memory`; agent-crew
must not depend on mnemos repository paths or internal database schemas.

| agent-crew | mnemos | Required features | Optional features | Notes |
|---|---|---|---|---|
| current `main` | mnemos with `capture`, `search`, `read`, and `capabilities --json` | `capture`, `search`, `read`, bounded CLI execution, graceful no-backend behavior | `search --fast --json`, `recall --json`, `feedback --json`, scored retrieval, `gc` support | Preferred pairing. Fast search uses the stable JSON API; Recall V2 is gated by `AGENT_CREW_MEMORY_RECALL_MODE`. |
| current `main` | older mnemos without `capabilities --json` | `capture`, `search`, `read` | legacy local FTS fallback when enabled | Supported with degradation. Direct FTS fallback is deprecated. |
| current `main` | no mnemos installed | none | none | Supported. Memory operations become no-op or best-effort warnings. |
| current `main` | unknown or partially broken mnemos | any working subset | none | Supported with warnings from `crew doctor` / `crew config dump --effective`. |

## Required CLI Behavior

mnemos should provide these stable commands:

```bash
mnemos capabilities --json
mnemos capture ...
mnemos search ...
mnemos read <id>
```

For fast search, mnemos should additionally support:

```bash
mnemos search --fast --json --limit 5 "query"
```

For Recall V2 and feedback experiments, mnemos should additionally support:

```bash
mnemos recall --json ...
mnemos feedback --json ...
```

The JSON output can be either a list of results or an object containing
`results` or `items`. Each result must expose an id field and a text field; a
`score` field is optional.

## Optional Capabilities

- Scored retrieval with `score` in `0..1`.
- Fast JSON search advertised by `mnemos capabilities --json`.
- JSON recall and feedback advertised by `mnemos capabilities --json`.
- Local memory garbage collection through agent-crew's `memory gc` helper.
- Instruction sync commands used by `crew:sync-instructions`.

## Graceful Degradation

| Condition | Behavior |
|---|---|
| mnemos missing | `core/bin/memory` exits successfully after a warning for non-critical paths. |
| mnemos too old to advertise capabilities | Wrapper falls back to regular `mnemos search`; legacy FTS fallback remains available but deprecated. |
| fast JSON search fails or returns invalid JSON | Wrapper falls back to legacy FTS or regular search. |
| Recall V2 capability missing | `AGENT_CREW_MEMORY_RECALL_MODE=v2` reports `incompatible_provider` and proceeds without memory unless strict mode is enabled. |
| Recall disabled | `AGENT_CREW_MEMORY_RECALL_MODE=off` performs no provider call. |
| capture times out | Workflow continues after warning. |
| capture succeeds locally but vault sync fails | Workflow continues and reports the local id when available. |
| read/search backend failure | Caller receives the backend status unless a documented non-blocking path applies. |

## Diagnostics

`crew doctor` and `crew config dump --effective` report mnemos command
availability, version detectability, and whether stable fast JSON search is
advertised. Unknown versions are warnings, not blockers, because agent-crew
supports no-backend and partial-backend operation.

`crew update` keeps this compatibility boundary by installing the current
`core/bin/memory` wrapper and documentation. It does not rewrite or inspect
mnemos storage.
