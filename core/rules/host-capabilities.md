# Host Capabilities Contract (Index)

## Purpose

`agent-crew` is provider-neutral. Each host adapter (Claude Code, Codex,
generic, future hosts) advertises a set of capability flags; core code
gates host-specific code paths behind these flags and falls back to a
file-based path when a flag is false. This file is the registry — the
detailed contract for each flag lives at
`core/rules/capabilities/{flag}.md`.

## The Three Invariants

1. **`core/` never directly calls host-specific tools.** Every
   host-specific call must be gated behind a capability flag, with a
   working fallback for the flag-false case.
2. **Adding a capability requires a four-piece set:**
   (a) a capability doc under `core/rules/capabilities/`,
   (b) provider-neutral scripts under `core/scripts/` if applicable,
   (c) an adapter implementation OR an explicit absence advertisement,
   (d) an entry in the Capability Registry below.
3. **`core/` markdown files never name host-specific tool identifiers**
   (for example, the names of any host's native question, task, or
   plan-mode tools). They name abstract capability intents only. The
   tool-name mapping lives in `adapters/{host}/invocation.md` or the
   adapter's `SKILL.md`.

## Capability Registry

| Flag | Status | Purpose (one line) | Detail doc |
|---|---|---|---|
| `task_tools`          | implemented | Host task lifecycle tools — observability mirror + approval signal carrier | `capabilities/task-tools.md` |
| `agent_background`    | implemented | Background subagent fan-out (parallel supervisor spawn) | `capabilities/agent-background.md` |
| `monitor_tool`        | implemented   | Streaming output surface over background processes | `capabilities/monitor-tool.md` |
| `reasoning_tier`      | install-time  | Per-agent abstract compute tier; adapter materializes to a host model | `capabilities/reasoning-tier.md` |
| `cost_tracking`       | implemented   | Per-task token usage reporting (powers cost circuit breaker, telemetry) | `capabilities/cost-tracking.md` |
| `hook_system`         | implemented | Host enforces validators at lifecycle moments (PreToolUse, PostToolUse) | `capabilities/hook-system.md` |
| `interactive_question`| conditional | Structured user-choice prompts (abstracts native question tools) | `capabilities/interactive-question.md` |

"Implemented" means the flag is consumed by current core code. "Planned"
means the capability doc records the contract but consumers are
introduced by a later refactor phase. **"Install-time"** means the
capability is honored by the adapter's `setup.sh` only; there is no
runtime gating or `capabilities.json` entry.

## File Location & Schema

```
${AGENT_CREW_HOME}/state/${PROJECT_NAME}/capabilities.json
```

- Written by the host adapter's `setup.sh` (e.g., `adapters/claude/setup.sh`).
- Read by the core pipeline (supervisor, `crew:status`, etc.) at runtime.
- Per-project: a `crew:setup` reset wipes the project state directory,
  which removes `capabilities.json` along with it — the next setup
  re-creates it.

```json
{
  "host": "<adapter name>",
  "task_tools":           true,
  "agent_background":     true,
  "monitor_tool":         true,
  "cost_tracking":        false,
  "hook_system":          true,
  "interactive_question": false,
  "interactive_question_mode": "codex_plan_mode_conditional"
}
```

| Field | Type | Notes |
|---|---|---|
| `host` | string | Adapter name that wrote the file. Informational; never used for gating. |
| `<flag>` | bool | See the per-flag detail doc in the Capability Registry table. |
| `<flag>_mode` | string | Optional adapter-specific conditional mode detail. Boolean flags remain authoritative. |

Any missing flag defaults to `false`. The `host` field is informational
only — invariant 1 forbids gating any code path on `host`.

## Absence Contract (global)

> **If `capabilities.json` does not exist, every flag is treated as `false`.**

Pre-existing installations that predate any given flag must continue to
work unchanged. Consumers MUST therefore treat a missing file exactly
like an all-false file. The canonical loader snippet is documented in
`capabilities/task-tools.md` (Absence Behavior section) and is
identical for every consumer.

## Producer Contract (host adapter)

A host adapter's `setup.sh` MUST:

1. Compute `${STATE_DIR}` as
   `${AGENT_CREW_HOME}/state/$(basename "${PROJECT_ROOT}")`.
2. `mkdir -p "${STATE_DIR}"` (idempotent).
3. Overwrite `${STATE_DIR}/capabilities.json` with the adapter's truthful
   flags.
   - Writing the file on every setup keeps the flags in sync with the
     installed adapter version.
   - The adapter MUST only set a flag to `true` when the host genuinely
     exposes the corresponding surface — never speculatively.
4. Print a `CAPABILITIES: <path>` line on stdout for operator
   visibility.

Adapters that do not have any of the advertised surfaces (e.g.,
`generic`) MAY skip writing the file entirely. The Absence Contract
above ensures the pipeline still works.

## Consumer Contract (core pipeline)

A consumer of the capability surface (supervisor, `crew:status`,
future orchestrator code) MUST:

1. Resolve `capabilities.json` via the location above.
2. Treat any I/O or JSON parse error as "all flags false".
3. Gate every host-specific code path behind a capability check.
   Direct, ungated calls to host-specific tools are forbidden by
   invariant 1.
4. Continue to write the file-based source of truth (`pipeline.json`,
   `progress.log`, `result.md`, `approval.md`) regardless of any
   capability flag. The capability layer is observability + optional
   acceleration; the file-based truth is always present.

## Stderr Mirroring (capability-independent)

The supervisor mirrors every `progress.log` append to `stderr`. This
behavior is **not** gated by any flag because it is host-agnostic:
streaming-capable hosts surface stderr automatically, and other hosts
simply see it on the terminal. Stderr mirroring is described in
`core/agents/supervisor.md`.

## Related Files

Per-flag detail (see Capability Registry table for the flag → doc
mapping):

- `core/rules/capabilities/task-tools.md`
- `core/rules/capabilities/agent-background.md`
- `core/rules/capabilities/monitor-tool.md`
- `core/rules/capabilities/reasoning-tier.md`
- `core/rules/capabilities/cost-tracking.md`
- `core/rules/capabilities/hook-system.md`
- `core/rules/capabilities/interactive-question.md`

Producers:

- `adapters/claude/setup.sh` (writes all currently-true flags)
- `adapters/codex/setup.sh`, `adapters/generic/setup.sh` (may skip
  writing entirely)

For new adapter authors: see `docs/adapter-authoring.md` for the
step-by-step guide on writing a new host adapter (required files,
capability declaration, invocation mapping, testing checklist).
