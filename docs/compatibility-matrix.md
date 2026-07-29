# agent-crew / mnemos Compatibility Matrix

This matrix documents the supported memory-provider boundary between
agent-crew and mnemos. The stable contract is `core/bin/memory`; agent-crew
must not depend on mnemos repository paths or internal database schemas.

| agent-crew | mnemos | Required features | Optional features | Notes |
|---|---|---|---|---|
| current `main` | mnemos with `capture`, `search`, `read`, `capabilities --json`, `recall --json`, and `feedback --json` | `capture`, `read`, bounded CLI execution, Recall V2, Feedback V1, graceful no-backend behavior | provider `search` for explicit legacy/shadow diagnostics, provider `gc` support | Preferred pairing. Recall V2 is the default memory path. |
| current `main` | older mnemos without Recall V2 capabilities | `capture`, `search`, `read` | explicit `AGENT_CREW_MEMORY_RECALL_MODE=legacy` compatibility | Default V2 reports `incompatible_provider` and continues without memory. Agent Crew no longer reads Mnemos storage directly. |
| current `main` | no mnemos installed | none | none | Supported. Memory operations become no-op or best-effort warnings. |
| current `main` | unknown or partially broken mnemos | any working subset | none | Supported with warnings from `crew doctor` / `crew config dump --effective`. |

## Required CLI Behavior

mnemos should provide these stable commands:

```bash
mnemos capabilities --json
mnemos read <id>
mnemos capture ...
mnemos recall --json --request-file <file>
mnemos feedback --json --request-file <file>
```

For explicit legacy/shadow diagnostics, mnemos may additionally support:

```bash
mnemos search ...
```

Recall V2 JSON must be an object containing provider status and result rows.
Agent Crew preserves provider scoring fields and does not synthesize fallback
relevance scores.

## Optional Capabilities

- JSON recall and feedback advertised by `mnemos capabilities --json`.
- Local memory garbage collection through provider `mnemos gc`.
- Instruction sync commands used by `crew:sync-instructions`.

## Graceful Degradation

| Condition | Behavior |
|---|---|
| mnemos missing | `core/bin/memory` exits successfully after a warning for non-critical paths. |
| mnemos too old to advertise Recall V2 capabilities | Default V2 reports `incompatible_provider` and proceeds without memory unless strict mode is enabled. Use explicit `AGENT_CREW_MEMORY_RECALL_MODE=legacy` for temporary text-search compatibility. |
| Recall V2 returns invalid JSON | Default V2 reports `invalid_json` and proceeds without memory unless strict mode is enabled. |
| Recall V2 capability missing | Default V2 reports `incompatible_provider` and proceeds without memory unless strict mode is enabled. |
| Recall disabled | `AGENT_CREW_MEMORY_RECALL_MODE=off` performs no provider call. |
| capture times out | Workflow continues after warning. |
| capture succeeds locally but vault sync fails | Workflow continues and reports the local id when available. |
| read/search backend failure | Caller receives the backend status unless a documented non-blocking path applies. |

## Diagnostics

`crew doctor` and `crew config dump --effective` report mnemos command
availability, version detectability, and whether Recall V2 is advertised.
Unknown versions are warnings, not blockers, because agent-crew
supports no-backend and partial-backend operation.

`crew update` keeps this compatibility boundary by installing the current
`core/bin/memory` wrapper and documentation. It does not rewrite or inspect
mnemos storage.
