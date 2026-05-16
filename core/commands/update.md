# crew:update - Refresh installed agent-crew assets from source repo

## Purpose

`crew:update` re-runs the host adapter installation against the current
source repository to refresh installed agents, hooks, rules, commands,
skills, and adapter scripts under `~/.agent-crew/` and the host-specific
location (e.g. `~/.claude/agent-crew/` for the Claude adapter).

It complements `crew:setup`:

| Command       | Purpose                                          | State reset prompt |
|---------------|--------------------------------------------------|--------------------|
| `crew:setup`  | First-time install or fresh project init         | Yes (if state exists) |
| `crew:update` | Refresh installed assets from a newer source repo| No (always preserves state) |

Unlike `crew:setup`, this command:

- Never prompts to reset per-project state under `~/.agent-crew/state/`.
- Never deletes extraneous files at the install destination.
- Uses Claude Code's native Edit and Write tools for all file content updates,
  so every changed file shows a native diff in the Claude Code UI automatically.
- Is idempotent: re-running with no source changes produces no edits.
- Does not alter `~/.claude/settings.json` hook configuration beyond what
  the original `install.sh` already does (it reuses the same marker-merge
  logic).

## State Paths

```bash
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
```

## Source Repository Discovery

The command must locate the agent-crew source repo (the local checkout of
this project) so it can re-run `install.sh`. Resolution order:

1. `AGENT_CREW_SOURCE_DIR` env var if set.
2. The git toplevel of the CWD if it contains both `core/` and `adapters/`
   subdirectories (i.e. the user invoked `crew:update` from inside the
   agent-crew source checkout).
3. A previously-recorded source path at `${AGENT_CREW_HOME}/source.path`
   (written by an earlier `crew:setup` or `crew:update` run — optional).
4. Fall back to error: ask the user to set `AGENT_CREW_SOURCE_DIR`.

```bash
resolve_source_dir() {
  if [ -n "${AGENT_CREW_SOURCE_DIR:-}" ] && [ -d "${AGENT_CREW_SOURCE_DIR}/core" ]; then
    echo "${AGENT_CREW_SOURCE_DIR}"; return 0
  fi
  local toplevel
  toplevel=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
  if [ -n "${toplevel}" ] && [ -d "${toplevel}/core" ] && [ -d "${toplevel}/adapters" ]; then
    echo "${toplevel}"; return 0
  fi
  if [ -f "${AGENT_CREW_HOME}/source.path" ]; then
    local rec
    rec=$(head -1 "${AGENT_CREW_HOME}/source.path")
    if [ -n "${rec}" ] && [ -d "${rec}/core" ]; then
      echo "${rec}"; return 0
    fi
  fi
  return 1
}
```

## Execution

1. Resolve `SOURCE_DIR` using the rules above. If unresolved, print:

   ```text
   crew:update — could not find the agent-crew source repo.
   Set AGENT_CREW_SOURCE_DIR to the local path of the agent-crew checkout
   and re-run, or run crew:update from inside the source checkout.
   ```

   and stop. Do NOT touch any installed files.

2. Establish path variables:

   ```bash
   SOURCE_DIR="${SOURCE_ROOT}/core"
   ADAPTERS_DIR="${SOURCE_ROOT}/adapters"
   AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
   CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"
   ```

3. For each file category below, enumerate source files with `find` (Bash),
   then use the **Read** tool to read each source file and the **Write** or
   **Edit** tool to write it to the destination. This gives every changed file
   a native diff display in the Claude Code UI — no custom diff code needed.

   Bash is used only for:
   - `mkdir -p` (create destination directories)
   - `chmod +x` (make shell scripts executable)
   - `find` (enumerate files to copy)
   - `settings.json` hook registration (python3 merge helpers from `install.sh`)

   **File categories and their source → destination mappings:**

   | Category | Source | Destination (primary) | Destination (compat alias) |
   |---|---|---|---|
   | commands | `${SOURCE_DIR}/commands/` | `${AGENT_CREW_HOME}/system/commands/` | `${AGENT_CREW_HOME}/commands/` |
   | rules | `${SOURCE_DIR}/rules/` | `${AGENT_CREW_HOME}/system/rules/` | `${AGENT_CREW_HOME}/rules/` |
   | hooks | `${SOURCE_DIR}/hooks/` | `${AGENT_CREW_HOME}/system/hooks/` | `${AGENT_CREW_HOME}/hooks/` |
   | scripts | `${SOURCE_DIR}/scripts/` | `${AGENT_CREW_HOME}/system/scripts/` | `${AGENT_CREW_HOME}/scripts/` |
   | setup | `${SOURCE_DIR}/setup/` | `${AGENT_CREW_HOME}/system/setup/` | `${AGENT_CREW_HOME}/setup/` |
   | adapters | `${ADAPTERS_DIR}/` | `${AGENT_CREW_HOME}/system/adapters/` | `${AGENT_CREW_HOME}/adapters/` |
   | agents | `${SOURCE_DIR}/agents/` | `${AGENT_CREW_HOME}/system/agents/` | (via sync_system_agents) |

   **Subdirectory categories:** `rules/` contains a `capabilities/`
   subdirectory (per-flag detail docs); `scripts/` may be flat or contain
   subdirectories. Enumeration of files in these categories MUST be
   recursive (use `find -type f`, not a flat glob). Destination paths
   MUST preserve the relative path from the source root so subdirectories
   are recreated under the destination.
   | claude hooks | `${AGENT_CREW_HOME}/hooks/` | `${CLAUDE_DIR}/agent-crew/hooks/` | — |
   | claude rules | `${AGENT_CREW_HOME}/rules/` | `${CLAUDE_DIR}/agent-crew/rules/` | — |
   | claude setup | `${AGENT_CREW_HOME}/setup/` | `${CLAUDE_DIR}/agent-crew/setup/` | — |
   | claude commands | `${AGENT_CREW_HOME}/commands/` | `${CLAUDE_DIR}/commands/` | — |
   | claude agents | `${AGENT_CREW_HOME}/system/agents/` | `${CLAUDE_DIR}/agent-crew/agents/` | — |

   For each file in a category:

   ```
   1. Read the file at source path using the Read tool.
   2. If destination file exists: use Edit to update it (shows diff in UI).
      If destination file does not exist: use Write to create it.
   3. After writing all files in a category, run:
      chmod +x "${DEST_DIR}/"*.sh 2>/dev/null || true
   ```

   **Agent layer enforcement** (use Bash, not Read/Write):

   After writing agents, run `sync_system_agents` to prune stale agents that
   were removed from the source repo:

   ```bash
   . "${SOURCE_DIR}/setup/common.sh"
   sync_system_agents \
     "${SOURCE_DIR}/agents" \
     "${AGENT_CREW_HOME}/system/agents" \
     "mcp-manager.md"
   ```

   Then merge system + user agents into the discovery destination:

   ```bash
   merge_agents_to_discovery \
     "${AGENT_CREW_HOME}/system/agents" \
     "${AGENT_CREW_HOME}/user/agents" \
     "${CLAUDE_DIR}/agents"
   ```

3.5. **Phase C3.0 Migration — Remove Stale `task-runner` Files**

   The `task-runner` agent was renamed to `supervisor` in Phase C3.0.
   `sync_system_agents` and `merge_agents_to_discovery` auto-prune two of the
   four installation paths; the other two are copied via `cp -R src/. dest/`
   which overwrites but does not delete. Defensively remove all four
   locations so the host never sees both the old and the new agent.

   The block is idempotent — `rm -f` is silent on missing files. After the
   first successful `crew:update` post-C3.0 it becomes a no-op.

   ```bash
   migrate_remove_stale_task_runner() {
     local removed=0
     local f
     local PROJECT_ROOT_LOCAL
     PROJECT_ROOT_LOCAL="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
     for f in \
       "${AGENT_CREW_HOME}/system/agents/task-runner.md" \
       "${CLAUDE_DIR}/agents/task-runner.md" \
       "${CLAUDE_DIR}/agent-crew/agents/task-runner.md" \
       "${PROJECT_ROOT_LOCAL}/.codex/agents/task-runner.toml"
     do
       if [ -f "${f}" ]; then
         rm -f "${f}"
         printf '[crew:update] Removed stale agent file: %s\n' "${f}"
         removed=$((removed + 1))
       fi
     done
     if [ "${removed}" -eq 0 ]; then
       printf '[crew:update] No stale task-runner files found (already migrated).\n'
     fi
   }
   migrate_remove_stale_task_runner
   ```

   > **Note:** the literal token `task-runner` survives intentionally inside
   > this migration block — it is the name of the OLD file being removed.
   > Verification greps must allow this single occurrence in `update.md`.

3.6. **Phase C2 Note — Supervisor sub-modules**

   Phase C2 split `supervisor.md` into an index plus three sibling content
   modules (`supervisor-bootstrap.md`, `supervisor-stages.md`,
   `supervisor-retry.md`). `sync_system_agents` and
   `merge_agents_to_discovery` handle these automatically because they sit
   at the top level of `core/agents/` (the same flat-glob copy that already
   moves `supervisor.md`). No migration code is required — the three new
   files arrive on the next `crew:update` and the host registers only
   `supervisor.md` as an agent (the others have no `name:` frontmatter).

3.7. **Phase 3.1 Migration — Remove Stale `scribe` Agent and Outline Hook**

   The `scribe` agent was a user-specific Outline / Plane / connect-docs
   integration that should never have been classified as a system agent.
   It is removed from the system layer in Phase 3.1; users who wrote
   custom scribe workflows must copy their version to
   `~/.agent-crew/user/agents/scribe.md` BEFORE running `crew:update`
   (this migration only removes the system copies). The paired
   `outline-posttooluse.sh` hook is also removed — it was passive (never
   wired into `settings.json`), so no hook unregistration is required.

   `sync_system_agents` and `merge_agents_to_discovery` auto-prune the
   agents at two of the four installation paths; the other two are copied
   via `cp -R src/. dest/` which overwrites but does not delete. Hooks
   are copied via `cp -R` at three paths. Defensively remove all
   locations so the host never sees the old scribe agent or outline hook
   script after migration.

   The block is idempotent — `rm -f` is silent on missing files. After
   the first successful `crew:update` post-3.1 it becomes a no-op. The
   literal tokens `scribe` and `outline-posttooluse` survive inside this
   migration block intentionally; verification greps must allow these
   occurrences in `update.md` (same convention as the C3.0 `task-runner`
   block above).

   ```bash
   migrate_remove_stale_scribe_and_outline_hook() {
     local removed=0
     local f
     local PROJECT_ROOT_LOCAL
     PROJECT_ROOT_LOCAL="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

     # Pre-removal warning if scribe is in system/ but absent from user/
     if [ -f "${AGENT_CREW_HOME}/system/agents/scribe.md" ] \
        && [ ! -f "${AGENT_CREW_HOME}/user/agents/scribe.md" ]; then
       printf '[crew:update] WARNING: scribe.md is being removed from system/ but no user/ copy exists.\n'
       printf '             If you use scribe, run BEFORE re-running crew:update:\n'
       printf '               cp "%s" "%s"\n' \
         "${AGENT_CREW_HOME}/system/agents/scribe.md" \
         "${AGENT_CREW_HOME}/user/agents/scribe.md"
       printf '             Continuing in 3s (Ctrl-C to abort)...\n'
       sleep 3
     fi

     # Stale scribe agent — four installation paths
     for f in \
       "${AGENT_CREW_HOME}/system/agents/scribe.md" \
       "${CLAUDE_DIR}/agents/scribe.md" \
       "${CLAUDE_DIR}/agent-crew/agents/scribe.md" \
       "${PROJECT_ROOT_LOCAL}/.codex/agents/scribe.toml"
     do
       if [ -f "${f}" ]; then
         rm -f "${f}"
         printf '[crew:update] Removed stale agent file: %s\n' "${f}"
         removed=$((removed + 1))
       fi
     done

     # Stale outline-posttooluse hook — three installation paths
     for f in \
       "${AGENT_CREW_HOME}/system/hooks/outline-posttooluse.sh" \
       "${AGENT_CREW_HOME}/hooks/outline-posttooluse.sh" \
       "${CLAUDE_DIR}/agent-crew/hooks/outline-posttooluse.sh"
     do
       if [ -f "${f}" ]; then
         rm -f "${f}"
         printf '[crew:update] Removed stale hook script: %s\n' "${f}"
         removed=$((removed + 1))
       fi
     done

     if [ "${removed}" -eq 0 ]; then
       printf '[crew:update] No stale scribe / outline-posttooluse files found (already migrated).\n'
     else
       printf '[crew:update] Phase 3.1 migration removed %d stale file(s).\n' "${removed}"
     fi
   }
   migrate_remove_stale_scribe_and_outline_hook
   ```

   > **User-data preservation:** if a user has placed their own
   > customized `scribe.md` at `~/.agent-crew/user/agents/scribe.md`, it
   > is preserved — the migration only touches `system/` and the
   > generated discovery mirrors. The user copy continues to be merged
   > into `~/.claude/agents/scribe.md` by `merge_agents_to_discovery` on
   > subsequent updates.

   > **Hook registration:** `outline-posttooluse.sh` was never registered
   > as a `PostToolUse` hook in either `install.sh` or
   > `adapters/claude/setup.sh` (verified during Phase 3.1 audit). No
   > `settings.json` rewrite is needed — removing the script alone is
   > sufficient.

4. Re-run the host adapter against the current project so any project-local
   files (e.g. `~/.claude/agent-crew/`) are also refreshed:

   ```bash
   PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   AGENT_CREW_MODE=update \
     bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "${PROJECT_ROOT}"
   ```

5. Record the resolved source path so future invocations of `crew:update`
   and the auto-sync step in `crew:run` can find it without `AGENT_CREW_SOURCE_DIR`.
   Always record `SOURCE_ROOT` (the repo root containing `core/` and `adapters/`),
   not `SOURCE_DIR` (the `core/` subdirectory):

   ```bash
   printf '%s\n' "${SOURCE_ROOT}" > "${AGENT_CREW_HOME}/source.path"
   ```

6. Update settings.json hook registrations (idempotent):

   ```bash
   AGENT_CREW_MODE=update AGENT_CREW_SOURCE_DIR="${SOURCE_DIR}" \
     bash "${SOURCE_DIR}/install.sh"
   ```

   This re-runs the marker-merge helpers so any newly added hooks are
   registered without duplicating existing entries.

## Safety Guarantees

- `${AGENT_CREW_HOME}/state/` is NEVER touched. The Read/Write approach
  targets only the categories listed above, which never overlap with state.
- The state directory marker file `${STATE_DIR}/tasks/active` (if present
  from an in-flight crew task) is preserved.
- Write/Edit operations are idempotent: unchanged files produce no diff.
- Any locally-created custom agents at `~/.agent-crew/user/agents/` are
  preserved — `sync_system_agents` and `merge_agents_to_discovery` only
  operate on the `system/agents/` layer.

## Migration Notes

### Phase 3.2 — `reasoning_tier` materialization

System agents now declare a `reasoning_tier` (`deep` / `balanced` /
`light`) in their frontmatter. On `crew:update`, the Claude adapter
rewrites the `model:` line of each installed agent at
`~/.claude/agents/*.md` to a concrete model identifier based on the
declared tier (see `core/rules/capabilities/reasoning-tier.md`).

Source files under `core/agents/` keep `model: inherit` and are not
changed. User agents under `~/.agent-crew/user/agents/` are left
untouched — user-owned files retain whatever `model:` value they
have. Agents without YAML frontmatter (e.g. `korean-normalizer.md`)
are silently skipped.

If you previously hand-edited `~/.claude/agents/*.md` to set a custom
`model:` for a system agent, your edit will be overwritten on the
next update. Move the agent to `~/.agent-crew/user/agents/` (and
rename it to avoid the system filename collision) to preserve a
manual model choice.

The Codex adapter does NOT currently materialize `reasoning_tier` —
Codex's per-agent TOML schema does not honor a per-agent model field
today. The tier remains declared in the Codex TOMLs for forward
compatibility but is advisory only on Codex.

### Phase 3.3 — `cost_tracking` capability + cost circuit breaker

The Claude adapter now advertises `cost_tracking: true` in
`capabilities.json` and registers `cost-tracker.sh` as a `PostToolUse`
hook in `~/.claude/settings.json`. On the next `crew:update`:

- `adapters/claude/setup.sh` re-writes `capabilities.json` with the
  new flag set to `true`. Existing files without the field default
  to `false` per the Absence Contract, so until update runs, the
  supervisor treats cost tracking as disabled — old installations
  continue to work unchanged.
- The `PostToolUse` registration for `cost-tracker.sh` is idempotent
  (mirrors the existing `agent-diff-post.sh` pattern). Re-running
  `crew:update` is safe.
- `core/scripts/cost-aggregate.py` is a new file — copied alongside
  other scripts under `${AGENT_CREW_HOME}/scripts/`.
- The legacy `~/.agent-crew/metrics/costs.jsonl` file (written by the
  pre-3.3 `cost-tracker.sh`) is **NOT** automatically migrated. The
  new hook writes to per-task files under
  `${STATE_DIR}/cost/<TASK_ID>.jsonl` instead. Users who want to keep
  the historical session-scoped data can leave `metrics/costs.jsonl`
  in place; the new `crew:cost` does not read it but does not delete
  it either.
- No manual intervention is needed: a fresh `crew:update` flips all
  the relevant pieces atomically.

User-facing config:

- `AGENT_CREW_BUDGET_DEEP`, `AGENT_CREW_BUDGET_BALANCED`,
  `AGENT_CREW_BUDGET_LIGHT` env vars override per-tier budgets.
  Defaults: 200,000 / 150,000 / 100,000 tokens. See
  `core/rules/quality-loop.md` § Cost Circuit Breaker.

Codex and generic adapters: no change. `cost_tracking` remains
`false` (implicit via absence from their `capabilities.json` or
absence of the file entirely). `crew:cost` prints a one-paragraph
fallback note on those adapters.

## Completion Message

```text
agent-crew updated.
Source : {SOURCE_DIR}
Install: ~/.agent-crew  (and ~/.claude/agent-crew when claude adapter active)

Usage:
  crew:run "request"    # business as usual
```
