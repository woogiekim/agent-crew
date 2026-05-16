# crew:agent — Direct Agent Invocation

Invoke a named agent directly — without the full crew:run → supervisor →
pipeline orchestration overhead. No worktree, no pipeline.json, no TASK_DIR
state. The result is displayed inline and returned to the caller.

## When to use crew:agent vs crew:run

| Scenario | Command |
|---|---|
| Simple, focused task for one specialist | `crew:agent <name> "task"` |
| Any task needing planning + multi-stage review | `crew:run "task"` |
| Multiple independent tasks | `crew:run "A" \| "B"` |
| Unknown scope / not sure which agent fits | `crew:run "task"` (supervisor decides) |

Use `crew:agent` when you already know which specialist is the right fit and
the task is self-contained (no cross-agent handoff needed).

## Syntax

```text
crew:agent <agent-name> "task description"
crew:agent --list
```

### Examples

```text
crew:agent backend "add a health check endpoint at /actuator/health"
crew:agent planner "design the caching layer for the user-service API"
crew:agent designer "create a wireframe spec for the checkout flow"
crew:agent frontend "add a loading skeleton to the product listing page"
crew:agent analyst "explain the current domain model and identify seams"
```

## Agent Safety Classification

Not every agent is safe to invoke directly. Some agents depend on prior stage
outputs or require the supervisor's approval gate.

### Safe for direct invocation

These agents are self-contained and can operate on the current working tree
without supervisor context:

| Agent | Typical use |
|---|---|
| `backend` | Implement or modify server-side code, endpoints, domain logic |
| `frontend` | Implement or modify UI components and client-side code |
| `planner` | Design, architecture analysis, task decomposition (produces a plan, no code) |
| `designer` | Wireframes, API contracts, data-model specifications |
| `analyst` | Code analysis, domain-model explanation, risk assessment |
| `documenter` | Generate or update documentation for existing code |
| `learning-mentor` | Explain concepts, teach patterns, answer technical questions |
| `korean-normalizer` | Normalize Korean task text to English (utility agent) |

### Requires supervisor context — do NOT invoke directly

These agents depend on pipeline artifacts or approval gates that only the
supervisor provides. Invoking them directly produces incomplete or unsafe results:

| Agent | Why it needs supervisor |
|---|---|
| `reviewer` | Needs the prior stage diff + handoff.md to review against |
| `devops` | Requires the supervisor approval gate before destructive actions (deploy, push, merge) |
| `resolver` | Requires two conflicting git branches to merge |
| `requirements` | Designed as an interactive requirements-collection stage within crew:run |
| `supervisor*` | Orchestration agents — never invoked directly |

If you invoke a restricted agent, `crew:agent` will print a warning and stop.

## Execution Steps

### Step 1 — Parse arguments

```text
AGENT_NAME = first positional argument (before the quoted task string)
TASK_STRING = the quoted task description

If --list flag: skip to Step 2 (list mode)
If AGENT_NAME is empty: print usage and stop
If TASK_STRING is empty: print usage and stop
```

### Step 2 — List mode (--list)

When the user runs `crew:agent --list`, enumerate available agents:

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"

echo "Available agents:"
echo ""
echo "  Safe for direct invocation:"
for f in "${AGENT_CREW_HOME}/system/agents/"*.md \
          "${AGENT_CREW_HOME}/user/agents/"*.md; do
  [ -f "$f" ] || continue
  name=$(basename "$f" .md)
  # Skip supervisor sub-modules and restricted agents
  case "$name" in
    supervisor*|reviewer|devops|resolver|requirements) continue ;;
  esac
  echo "    crew:agent ${name} \"<task>\""
done

echo ""
echo "  Requires supervisor (use crew:run instead):"
echo "    reviewer, devops, resolver, requirements"
```

### Step 3 — Validate agent name

Check that the named agent exists in one of the two agent search paths:

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
SYSTEM_AGENTS="${AGENT_CREW_HOME}/system/agents"
USER_AGENTS="${AGENT_CREW_HOME}/user/agents"

AGENT_FILE=""
if [ -f "${USER_AGENTS}/${AGENT_NAME}.md" ]; then
  AGENT_FILE="${USER_AGENTS}/${AGENT_NAME}.md"
elif [ -f "${SYSTEM_AGENTS}/${AGENT_NAME}.md" ]; then
  AGENT_FILE="${SYSTEM_AGENTS}/${AGENT_NAME}.md"
fi

if [ -z "${AGENT_FILE}" ]; then
  echo "crew:agent: unknown agent '${AGENT_NAME}'"
  echo "Run 'crew:agent --list' to see available agents."
  exit 1
fi
```

### Step 4 — Safety gate

Refuse restricted agents before invoking:

```bash
RESTRICTED="reviewer devops resolver requirements supervisor supervisor-bootstrap supervisor-stages supervisor-retry"
for restricted in $RESTRICTED; do
  if [ "${AGENT_NAME}" = "${restricted}" ]; then
    echo "crew:agent: '${AGENT_NAME}' requires supervisor context."
    echo "Use 'crew:run \"${TASK_STRING}\"' instead."
    exit 1
  fi
done
```

### Step 5 — Invoke the agent

Run the named agent directly in the current working directory. No worktree
is created, no pipeline.json is written, and no TASK_DIR state is allocated.

Provide the agent with:

- `PROJECT_ROOT` — current git toplevel (or cwd if not a git repo)
- `TASK` — the user's task string (normalized if Korean; see Step 6)
- `MODE=direct` — signals to the agent that it is running outside the pipeline

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

Invoke the agent using the host's native agent-call mechanism (e.g., the
Claude Code `Task` tool). Pass as the agent prompt:

```text
You are running in MODE=direct (lightweight invocation via crew:agent).

PROJECT_ROOT: {PROJECT_ROOT}
TASK: {TASK}

Work in PROJECT_ROOT. Complete the task, commit any code changes to the
current branch, and return your result.

Do NOT create pipeline.json, progress.log, register.json, or any
~/.agent-crew/state/ entries. This is a lightweight, stateless invocation.

On completion, output:
  STATUS: completed
  SUMMARY: <one or two sentences describing what was done>
  FILES: <comma-separated list of created/modified files, or "none">
```

### Step 6 — Korean input normalization

If TASK_STRING contains Korean text, normalize it to English before passing
it to the agent (per `core/rules/korean-input.md`). Invoke the
`korean-normalizer` agent with the raw text and substitute its output for
TASK_STRING before Step 5.

### Step 7 — Display result

Display the agent's STATUS/SUMMARY/FILES output inline. No further
orchestration or approval prompts are issued unless the agent's task
includes destructive operations that require approval (in which case use
`crew:run` instead — see the safety classification table above).

## Lightweight guarantees

`crew:agent` provides the following guarantees that distinguish it from `crew:run`:

| Property | crew:run | crew:agent |
|---|---|---|
| New git branch / worktree | Yes (per task) | No — current branch |
| pipeline.json written | Yes | No |
| TASK_DIR state allocated | Yes | No |
| Multi-stage pipeline | Yes | No — single agent call |
| Supervisor orchestration | Yes | No |
| Reviewer stage | Yes (automatic) | No |
| Approval gate for destructive ops | Yes | Not applicable (devops restricted) |
| Cost tracking | Yes (capability-gated) | No |
| Telemetry / progress events | Yes | No |

Because `crew:agent` skips the reviewer stage, code produced by direct
invocation has not been independently verified. For production-bound changes,
use `crew:run` to get the full pipeline including the reviewer stage.

## Completion message

On success, display:

```text
crew:agent [{agent-name}] done.
{SUMMARY from agent}
Files: {FILES from agent}
```

On failure (agent returns STATUS other than completed):

```text
crew:agent [{agent-name}] did not complete.
{agent output}

To retry with full pipeline support: crew:run "{task description}"
```
