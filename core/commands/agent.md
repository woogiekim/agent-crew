# crew:agent — Direct Agent Invocation

Invoke a named agent directly — without the full crew:run → supervisor →
pipeline orchestration overhead. No worktree, no pipeline.json, no TASK_DIR
state. The result is displayed inline and returned to the caller.

Agent capability definitions and routing rules live in
**`core/rules/agent-routing.md`** (the DIP abstraction). This command depends
only on that abstraction — it does not hard-code any agent name in its logic.

## When to use crew:agent vs crew:run

| Scenario | Command |
|---|---|
| Simple, focused task and you know the right specialist | `crew:agent <name> "task"` |
| Simple, focused task — let routing pick the agent | `crew:agent "task"` |
| Any task needing planning + multi-stage review | `crew:run "task"` |
| Multiple independent tasks | `crew:run "A" \| "B"` |
| Unknown scope / not sure which agent fits | `crew:run "task"` (supervisor decides) |

Use `crew:agent` when the task is self-contained (no cross-agent handoff) and
either you know the right specialist or want auto-routing to pick one.

## Syntax

```text
crew:agent <agent-name> "task description"   # explicit mode
crew:agent "task description"                # auto-routing mode
crew:agent --list                            # list available agents (from agent-routing.md)
crew:agent --routing                         # show auto-routing rules table
```

### Examples

```text
# Explicit mode
crew:agent backend "add a health check endpoint at /actuator/health"
crew:agent planner "design the caching layer for the user-service API"
crew:agent designer "create a wireframe spec for the checkout flow"
crew:agent frontend "add a loading skeleton to the product listing page"
crew:agent analyst "explain the current domain model and identify seams"

# Auto-routing mode (agent selected from core/rules/agent-routing.md)
crew:agent "add a health check endpoint at /actuator/health"
crew:agent "design the caching layer"
crew:agent "explain the current domain model"
```

## Agent visibility — always shown before spawning

In **explicit mode**:
```
[crew:agent] → planner agent
              mode: explicit
              task: "design the caching layer"
```

In **auto-routing mode**:
```
[crew:agent] → backend agent
              reason: endpoint keyword matched backend routing rule (confidence: high)
              task: "add a health check endpoint"
```

The visibility line is **mandatory** — it is always emitted before the agent
is invoked so the user always knows what is running.

---

## Execution Steps

### Step 1 — Parse arguments and select mode

```text
RAW_ARGS = all positional arguments provided by the user

Special subcommands (check first):
  --list     → jump to Step 2a (list mode)
  --routing  → jump to Step 2b (routing rules mode)

Otherwise:
  Consult the Agent Registry in core/rules/agent-routing.md.
  Does RAW_ARGS[0] match a known agent name in the registry?
    YES → EXPLICIT MODE:  AGENT_NAME = RAW_ARGS[0], TASK_STRING = RAW_ARGS[1]
    NO  → AUTO-ROUTING MODE: TASK_STRING = RAW_ARGS[0]

  If TASK_STRING is empty in either mode: print usage and stop.
```

### Step 2a — List mode (--list)

When the user runs `crew:agent --list`, read the **Agent Registry** from
`core/rules/agent-routing.md` and enumerate agents grouped by invocation
safety.

Output format:
```
Available agents  (source: core/rules/agent-routing.md)

  Safe for direct invocation:
    crew:agent backend   "…"   — Server-side code, APIs, DB, domain logic
    crew:agent frontend  "…"   — UI components, client-side code, CSS, UX
    crew:agent planner   "…"   — Architecture, design, decomposition, analysis
    crew:agent designer  "…"   — Wireframes, UX specs, visual design
    crew:agent analyst   "…"   — Codebase understanding, domain investigation
    crew:agent documenter "…"  — Documentation, README, API docs
    crew:agent learning-mentor "…" — Concept explanation, teaching, Q&A
    crew:agent korean-normalizer "…" — Korean text normalization (utility)

  Requires supervisor context — use crew:run instead:
    reviewer       Requires completed stage output from supervisor context
    devops         Requires supervisor approval gate
    resolver       Requires git conflict state established by supervisor
    requirements   Interactive multi-round mode only valid inside supervisor
    supervisor     Is itself the orchestrator — recursive invocation forbidden
```

Do not hard-code this list. Derive it by reading the Agent Registry table
in `core/rules/agent-routing.md` at invocation time.

### Step 2b — Routing rules mode (--routing)

When the user runs `crew:agent --routing`, display the **Auto-Routing Rules**
table from `core/rules/agent-routing.md` verbatim, along with a brief
explanation of matching semantics.

Output format:
```
Auto-Routing Rules  (source: core/rules/agent-routing.md)

Rules are evaluated top-to-bottom; first match wins.

Priority | Pattern                          | Agent          | Confidence
---------|----------------------------------|----------------|----------
1        | deploy / push to / ci/cd / …     | BLOCKED        | —
2        | review / lint / approve / …      | BLOCKED        | —
3        | api / endpoint / server / …      | backend        | high
…

Use 'crew:agent "task"' (no agent name) to trigger auto-routing.
Use 'crew:agent --list' to see which agents are available.
```

### Step 3 — Validate agent (explicit mode only)

Look up `AGENT_NAME` in the **Agent Registry** (`core/rules/agent-routing.md`):

```text
1. If AGENT_NAME not found in registry:
     print: "crew:agent: unknown agent '${AGENT_NAME}'"
     print: "Run 'crew:agent --list' to see available agents."
     stop.

2. If found but Safe-for-direct-invocation = no:
     print: "crew:agent: '${AGENT_NAME}' cannot be invoked directly."
     print: "Reason: ${Reason-if-restricted from registry}"
     print: "Use 'crew:run \"${TASK_STRING}\"' instead."
     stop.

3. If found and safe: continue to Step 4.
```

Do not hard-code a restricted-agent list in this command. The restriction
information lives exclusively in `core/rules/agent-routing.md`.

### Step 4 — Auto-route (auto-routing mode only)

Apply the **Auto-Routing Rules** from `core/rules/agent-routing.md`
top-to-bottom against the normalized TASK_STRING (case-insensitive):

```text
For each rule in priority order:
  If pattern matches TASK_STRING:
    If rule target is BLOCK:
      print: "crew:agent: this task requires supervisor orchestration."
      print: "Reason: ${reason from rule}"
      print: "Use 'crew:run \"${TASK_STRING}\"' instead."
      stop.
    Else (agent assignment):
      AGENT_NAME  = rule target agent
      CONFIDENCE  = rule confidence
      ROUTE_REASON = rule reason text
      break.

If no rule matched (NONE):
  print: "crew:agent: cannot auto-route this task."
  print: "Specify an agent explicitly: crew:agent <name> \"${TASK_STRING}\""
  print: "Or delegate to the supervisor:  crew:run \"${TASK_STRING}\""
  stop.
```

### Step 5 — Korean input normalization

If TASK_STRING contains Korean text, normalize it to English before
proceeding (per `core/rules/korean-input.md`). Invoke the `korean-normalizer`
agent with the raw text and substitute its output for TASK_STRING. Then
re-evaluate from Step 3 or Step 4 as appropriate with the normalized string.

### Step 6 — Emit visibility line (mandatory)

Always emit this line before invoking the agent:

**Explicit mode:**
```
[crew:agent] → {AGENT_NAME} agent
              mode: explicit
              task: "{TASK_STRING}"
```

**Auto-routing mode:**
```
[crew:agent] → {AGENT_NAME} agent
              reason: {ROUTE_REASON} (confidence: {CONFIDENCE})
              task: "{TASK_STRING}"
```

This line is non-negotiable. The user must always know which agent is running
and why before the agent is spawned.

### Step 7 — Invoke the agent

Run the selected agent directly in the current working directory. No worktree
is created, no pipeline.json is written, and no TASK_DIR state is allocated.

Provide the agent with:

- `PROJECT_ROOT` — current git toplevel (or cwd if not a git repo)
- `TASK` — the normalized task string
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

### Step 8 — Display result

Display the agent's STATUS/SUMMARY/FILES output inline. No further
orchestration or approval prompts are issued (devops is restricted and
requires `crew:run`).

---

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

---

## Completion message

On success:
```
crew:agent [{agent-name}] done.
{SUMMARY from agent}
Files: {FILES from agent}
```

On failure (agent returns STATUS other than completed):
```
crew:agent [{agent-name}] did not complete.
{agent output}

To retry with full pipeline support: crew:run "{task description}"
```

---

## Adding a new agent

To make a new agent available via `crew:agent`:

1. Create the agent file under `~/.agent-crew/system/agents/` or
   `~/.agent-crew/user/agents/`.
2. Add a row to the **Agent Registry** in `core/rules/agent-routing.md`.
3. If auto-routing should reach it, add a row to the **Auto-Routing Rules**
   table in `core/rules/agent-routing.md`.
4. No changes to this file (`core/commands/agent.md`) are required.
