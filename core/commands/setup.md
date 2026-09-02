# crew:setup - Host Adapter Installation And Workspace Init

## Purpose

`crew:setup` initializes the current project for agent-crew and asks the neutral
host dispatcher to install the correct host adapter output.

This command intentionally does not know host-specific paths or formats. It
depends only on the dispatcher abstraction at `~/.agent-crew/setup/setup-host.sh`.
The dispatcher selects an adapter, and the adapter owns all host-specific
installation details.

Set `AGENT_CREW_HOST` to an adapter directory name to override automatic host
detection.

## State Paths

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --ensure \
  --migrate-legacy \
  --format shell)"
```

## Execution

1. Resolve `PROJECT_NAME`, canonical `PROJECT_ROOT`, collision-safe
   `PROJECT_STATE_KEY`, and `STATE_DIR` from the current directory.

2. If `{STATE_DIR}` already exists, ask how to handle existing state:
   - "Cancel" exits setup without making any changes.
   - "Reset runtime state and preserve project-context" removes task/runtime
     state and keeps `{STATE_DIR}/project-context/` (default).
   - "Archive project-context and reset runtime state" moves project context
     under `{STATE_DIR}/archive/project-context/` first.
   - "Full state reset" removes the whole project state directory.

3. Run the neutral host dispatcher (idempotent — safe to re-run):

   ```bash
   AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
   PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "${PROJECT_ROOT}"
   ```

   After the selected adapter has installed its global assets, the dispatcher
   scans only the current project for ownership-proven legacy assets from older
   project-local installations. It moves proven paths individually to a
   recoverable backup under
   `~/.agent-crew/backups/project-assets/{PROJECT_STATE_KEY}/` and preserves
   Git-tracked, changed, unknown, or explicit project-owned paths. If Git status
   cannot be verified, it performs no migration.

4. Initialize the state directory:

   ```bash
   AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
   PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
     --agent-crew-home "${AGENT_CREW_HOME}" \
     --project-root "${PROJECT_ROOT}" \
     --ensure \
     --migrate-legacy \
     --format shell)"
   mkdir -p "${STATE_DIR}/tasks"
   echo "setup_ok"
   ```

5. **Seed Channel B adapter skill templates** (idempotent — copy-if-absent).

   The framework ships canonical seed templates for dispatcher-pattern
   adapter skills under `core/agents/skills/templates/` (see
   `core/rules/agent-tool-dispatch.md` § Channel B template seeding).
   `crew:setup` seeds each template into `~/.agent-crew/user/skills/<name>.md`
   ONLY when the user-layer file does not already exist.

   The seed helper NEVER overwrites a user-edited file — this is the
   load-bearing invariant from commit `1f89c02`. The runtime contract
   (dispatcher loads `~/.agent-crew/user/skills/<name>.md`) is unchanged.

   ```bash
   AGENT_CREW_SEED_TAG="crew:setup" \
     bash "${AGENT_CREW_HOME}/setup/seed-skill-templates.sh"
   ```

   The helper resolves its own defaults:
   - Source: `${AGENT_CREW_HOME}/system/agents/skills/templates/`
     (falls back to `${AGENT_CREW_HOME}/agents/skills/templates/` for
     compat installations).
   - Destination: `${AGENT_CREW_HOME}/user/skills/`.

   When no templates are installed (fresh install with empty templates
   directory), the helper exits 0 silently — this is the expected
   steady-state when no dispatcher agents have shipped templates yet.

6. Print the completion message.

## Completion Message

```text
agent-crew workspace initialized.
Project: {PROJECT_NAME}
Project state key: {PROJECT_STATE_KEY}
State path: ~/.agent-crew/state/{PROJECT_STATE_KEY}/
Host adapter: {adapter name}

Usage:
  crew:run "request"    # run one task through the unified engine
```
