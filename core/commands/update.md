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
   | setup | `${SOURCE_DIR}/setup/` | `${AGENT_CREW_HOME}/system/setup/` | `${AGENT_CREW_HOME}/setup/` |
   | adapters | `${ADAPTERS_DIR}/` | `${AGENT_CREW_HOME}/system/adapters/` | `${AGENT_CREW_HOME}/adapters/` |
   | agents | `${SOURCE_DIR}/agents/` | `${AGENT_CREW_HOME}/system/agents/` | (via sync_system_agents) |
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

## Completion Message

```text
agent-crew updated.
Source : {SOURCE_DIR}
Install: ~/.agent-crew  (and ~/.claude/agent-crew when claude adapter active)

Usage:
  crew:run "request"    # business as usual
```
