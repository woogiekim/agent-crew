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
- Reports a per-file diff summary of what was updated vs unchanged.
- Is idempotent: re-running with no source changes reports 0 updated files.
- Does not alter `~/.claude/settings.json` hook configuration beyond what
  the original `install.sh` already does (it reuses the same marker-merge
  logic).

The convention `AGENT_CREW_MODE=update` is set in the environment so that
the dispatcher (`~/.agent-crew/setup/setup-host.sh`) and each adapter
`setup.sh` know they are running in update mode.

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

2. Snapshot the install destination(s) BEFORE update:

   ```bash
   AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
   CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"
   TMP_DIR=$(mktemp -d)
   bash "${AGENT_CREW_HOME}/setup/update-diff.sh" "${AGENT_CREW_HOME}" \
     > "${TMP_DIR}/before-agent-crew.snap" 2>/dev/null || true
   if [ -d "${CLAUDE_DIR}/agent-crew" ]; then
     bash "${AGENT_CREW_HOME}/setup/update-diff.sh" "${CLAUDE_DIR}/agent-crew" \
       > "${TMP_DIR}/before-claude.snap" 2>/dev/null || true
   fi
   ```

   The snapshot file lists every regular file at the destination, hashed
   with SHA256, sorted deterministically by path.

3. Run the installer in update mode (auto-confirms reinstall, preserves
   state, runs the host adapter again with `AGENT_CREW_MODE=update`):

   ```bash
   AGENT_CREW_MODE=update AGENT_CREW_SOURCE_DIR="${SOURCE_DIR}" \
     bash "${SOURCE_DIR}/install.sh"
   ```

4. Re-run the host adapter against the current project so any project-local
   files (e.g. `~/.claude/agent-crew/`) are also refreshed:

   ```bash
   PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   AGENT_CREW_MODE=update \
     bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "${PROJECT_ROOT}"
   ```

5. Record the resolved source path so future invocations of `crew:update`
   can find it without `AGENT_CREW_SOURCE_DIR`:

   ```bash
   printf '%s\n' "${SOURCE_DIR}" > "${AGENT_CREW_HOME}/source.path"
   ```

6. Snapshot the install destination(s) AFTER update and diff:

   ```bash
   bash "${AGENT_CREW_HOME}/setup/update-diff.sh" "${AGENT_CREW_HOME}" \
     > "${TMP_DIR}/after-agent-crew.snap"
   bash "${AGENT_CREW_HOME}/setup/update-diff.sh" diff \
     "${TMP_DIR}/before-agent-crew.snap" "${TMP_DIR}/after-agent-crew.snap"
   if [ -f "${TMP_DIR}/before-claude.snap" ]; then
     bash "${AGENT_CREW_HOME}/setup/update-diff.sh" "${CLAUDE_DIR}/agent-crew" \
       > "${TMP_DIR}/after-claude.snap"
     printf '\n[claude install location]\n'
     bash "${AGENT_CREW_HOME}/setup/update-diff.sh" diff \
       "${TMP_DIR}/before-claude.snap" "${TMP_DIR}/after-claude.snap"
   fi
   rm -rf "${TMP_DIR}"
   ```

7. Print the completion message.

## Safety Guarantees

- `${AGENT_CREW_HOME}/state/` is NEVER touched by `install.sh` or any adapter
  `setup.sh`. The diff snapshot intentionally includes the state path so
  the report will surface any accidental write — under normal operation it
  always reports 0 changes for state files.
- The state directory marker file `${STATE_DIR}/tasks/active` (if present
  from an in-flight crew task) is preserved.
- `${CLAUDE_DIR}/settings.json` hook configuration is reached only via the
  same marker-merge helpers used by `install.sh` — idempotent.
- `cp -R` overwrites destination files but does not delete extraneous files.
  Any locally-created custom agents at `~/.agent-crew/agents/` are preserved.

## Completion Message

```text
agent-crew updated.
Source : {SOURCE_DIR}
Install: ~/.agent-crew  (and ~/.claude/agent-crew when claude adapter active)

Diff summary:
  total: {N}
  updated: {U}
  added: {A}
  removed: {R}
  unchanged: {C}

Usage:
  crew:run "request"    # business as usual
```
