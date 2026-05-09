# ac:setup — Host Adapter Installation And Workspace Init

## Purpose

`ac:setup` initializes the current project for agent-crew and asks the neutral
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

2. Run the neutral host dispatcher:

   ```bash
   AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
   PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "${PROJECT_ROOT}"
   ```

3. If `{STATE_DIR}` already exists, ask for confirmation before resetting state:
   - "Cancel (Recommended)" exits setup.
   - "Reset" removes existing state and continues.

4. Initialize the state directory:

   ```bash
   AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
   STATE_DIR="${AGENT_CREW_HOME}/state/$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")"
   mkdir -p "${STATE_DIR}/tasks"
   echo "setup_ok"
   ```

5. Print the completion message.

## Completion Message

```text
agent-crew workspace initialized.
Project: {PROJECT_NAME}
State path: ~/.agent-crew/state/{PROJECT_NAME}/
Host adapter: {adapter name}

Usage:
  ac:crew "request"    # run one task through the unified engine
```
