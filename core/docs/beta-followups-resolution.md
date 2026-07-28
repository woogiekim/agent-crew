# Beta follow-ups resolution plan

This note resolves the open follow-up scope in:

- #66 — Third beta usability follow-ups for agent-crew and mnemos
- #67 — Codex routing speed and stabilization follow-ups

The scope is intentionally limited to tooling, docs, config, command wiring,
and validation assets. It does not change production product behavior.

## Status

| Area | Resolution | Evidence |
|---|---|---|
| Mnemos foreground search/capture can hang or trigger slow vault sync | Add a host-neutral bounded wrapper, a read-only FTS fast path for recall, local support-memory captures by default, and sub-second process polling so hooks, Codex skills, and manual recall paths fail visibly without sitting on Obsidian git sync. | `core/bin/memory`, `core/scripts/mnemos-bounded.sh`, `tests/shell/test_memory_wrapper.bash`, `tests/shell/test_mnemos_bounded.bash` |
| Codex mnemos preservation is manual | Codex remains hook-limited, so the supported path is explicit bounded recall before non-trivial work; failures are visible and non-blocking. | `core/bin/memory`, `core/scripts/mnemos-bounded.sh` |
| Stale global Codex agents | Global stubs are regenerated and pruned by the global adapter update path. Project-local stubs remain the preferred discovery surface for a workspace. | `core/scripts/update-global-adapters.sh`, `tests/shell/test_update_global_codex_agents.bash` |
| Runtime skill usage verification | Structural skill loading remains covered by tests; runtime verification is defined as beta evidence from pipeline logs and stage artifacts, not as production behavior. | `tests/shell/test_skill_loading_open_closed.bash`, checklist below |
| Codex routing speed | Keep Codex stubs thin, prefer project-local `.codex/agents`, and use cached command/capability paths where command definitions already materialize them. | `adapters/codex/template/agents/*.toml`, `core/commands/run.md` Step 0 |
| Background-agent readiness | Codex remains capability-gated with `agent_background=false`; future native background support must flip only the capability file and follow the P4 branch. | `core/rules/host-capabilities.md`, `adapters/codex/setup.sh` |
| `crew:status --collect` stabilization | File state is still the source of truth; collection diagnosis should start with `session.json`, `result.md`, `progress.log`, and `finalize-session.sh`. | `core/commands/status.md`, `core/scripts/finalize-session.sh` |

## Codex memory recall contract

Codex currently cannot rely on a trusted automatic hook path for mnemos context
in the same way Claude can. The supported Codex path is:

1. Before non-trivial work, run bounded recall through the memory wrapper:

   ```bash
   ~/.agent-crew/bin/memory search "<task keywords>" --limit 5
   ```

   The wrapper first uses the local mnemos FTS index read-only. It falls back
   to the bounded mnemos CLI only when the fast path is unavailable or disabled
   with `AGENT_CREW_MEMORY_FAST_SEARCH=0`.

2. Treat exit `124` as a visible memory backend timeout, not a workflow blocker.
3. Continue from local repo context if recall fails.
4. Capture substantive findings through the existing `memory` wrapper when
   possible; if capture times out, report the timeout and continue. Support
   captures default to mnemos's local backend so they remain fast and searchable
   without forcing Obsidian vault git sync on the critical path. Set
   `MNEMOS_BACKEND` explicitly to use a configured backend instead.

Default bounded CLI timeout is 8 seconds and can be tuned:

```bash
AGENT_CREW_MNEMOS_TIMEOUT_SECONDS=3 \
  bash core/scripts/mnemos-bounded.sh search "agent-crew"
```

## Runtime skill verification checklist

Use this checklist in beta runs where agent skill usage must be proven at
runtime:

- `planner` result references `pipeline-planning` or records stage composition
  criteria.
- `analyst` result references the relevant analysis skill for the task domain.
- Implementer stage artifacts show a required skill was loaded when its trigger
  matched.
- `test-writer` artifacts show test strategy selection from skill guidance.
- `reviewer` result contains an explicit review verdict and evidence paths.
- `progress.log` includes the phase/stage boundary around each skill-triggered
  stage.

If the checklist cannot be satisfied because the host did not expose runtime
skill-load events, record that as a beta limitation and attach the available
stage artifacts instead.

## Codex routing and stub precedence

Codex has three relevant discovery layers:

1. Project-local `.codex/agents/*.toml` — preferred for the active workspace.
2. Global `~/.codex/agents/*.toml` — fallback when no project-local stub exists.
3. Canonical Markdown under `~/.agent-crew/system/agents/*.md` — source of truth
   that TOML stubs should delegate to or mirror.

The update path must prune stale global files and refresh global stubs from the
current adapter template. `tests/shell/test_update_global_codex_agents.bash`
guards this by planting a stale `task-runner.toml` and asserting it is removed.

## `crew:status --collect` diagnosis

When collection appears stuck:

1. Check `${STATE_DIR}/session.json` for tasks still marked `running`.
2. For each running task, check `${TASK_DIR}/result.md` for terminal status.
3. Check `${TASK_DIR}/progress.log` for the last phase/stage boundary.
4. Run `bash core/scripts/finalize-session.sh "${SESSION_FILE}" "${STATE_DIR}"`
   on inline Codex/generic runs to reconcile terminal files back into
   `session.json`.
5. If a task lacks both progress and result files, classify it as a supervisor
   crash and resume through the normal supervisor retry path.

## Issue mapping

| Issue | Covered by |
|---|---|
| #66 follow-up 1 | `mnemos-bounded.sh` and visible timeout policy |
| #66 follow-up 2 | Codex bounded recall contract |
| #66 follow-up 3 | global Codex stub precedence + stale-prune test |
| #66 follow-up 4 | runtime skill verification checklist |
| #67 proposals 1, 4, 6 | routing/stub precedence and global sync validation |
| #67 proposals 2, 5 | capability-gated background behavior and collection diagnosis |
| #67 proposals 3, 7 | bounded recall and runtime skill verification checklist |
