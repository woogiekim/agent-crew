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
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
```

## Execution

1. Resolve `PROJECT_NAME` and `PROJECT_ROOT` from the current directory.

2. If `{STATE_DIR}` already exists, ask for confirmation before resetting state:
   - "Cancel (Recommended)" exits setup without making any changes.
   - "Reset" removes existing task state and continues with a clean slate.

3. Run the neutral host dispatcher (idempotent — safe to re-run):

   ```bash
   AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
   PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "${PROJECT_ROOT}"
   ```

4. Initialize the state directory:

   ```bash
   AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
   STATE_DIR="${AGENT_CREW_HOME}/state/$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")"
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
State path: ~/.agent-crew/state/{PROJECT_NAME}/
Host adapter: {adapter name}

Usage:
  crew:run "request"    # run one task through the unified engine
```
