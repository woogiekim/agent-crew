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
| Single-agent work and you know the right specialist | `crew:agent <name> "task"` |
| Single-agent work — let routing pick the agent | `crew:agent "task"` |
| Any task needing planning + multi-stage review | `crew:run "task"` |
| Multiple independent tasks | `crew:run "A" \| "B"` |
| Unknown scope / not sure which agent fits | `crew:run "task"` (supervisor decides) |

`crew:agent` may execute mutating work when the selected agent's own definition
allows mutation. Read-only guarantees are enforced by each agent definition,
not by this command. Use `crew:run` when the work needs supervisor planning,
parallelism, centralized approval, or the automatic reviewer stage.

When a direct agent request involves review comments, external feedback,
automation findings, refactoring, parity, or migration follow-up, apply
`core/rules/contract-first-feedback-fidelity.md` before any mutating agent acts.
Direct invocation still must preserve feedback intent, identify affected
contracts and side effects, and avoid literal changes that are not
`contract-safe`, `parity-safe`, `scope-safe`, and `side-effect-safe`.

## Syntax

```text
crew:agent [--host-bridge-command CMD] [--agent-layer project|user|system] <agent-name> "task description"   # explicit mode
crew:agent [--host-bridge-command CMD] [--save-agent-layer project|user|system] <agent-name> "task description"
crew:agent [--host-bridge-command CMD] "task description"                                                    # auto-routing mode
crew:agent --list                                                                                           # list available agents (from agent-routing.md)
crew:agent --routing                                                                                        # show auto-routing rules table
```

### Examples

```text
# Explicit mode
crew:agent analyst "explain the current domain model and identify seams"
crew:agent historian "what ran in this session?"
crew:agent mentor "explain the difference between a branch and a worktree"
crew:agent learning-mentor "explain dependency injection"   # legacy alias

# Auto-routing mode (agent selected from core/rules/agent-routing.md)
crew:agent "explain the current domain model"
crew:agent "what ran in this session?"
crew:agent "why did the router choose historian?"

# Same-name agent conflict
crew:agent analyst "분석해줘"
# STATUS: selection_required
# 1. 현재 프로젝트 전용 analyst
#    path: /repo/.agent-crew/project/agents/analyst.md
#    scope: 이 저장소에서만 사용
# 2. 내 개인 기본 analyst
#    path: ~/.agent-crew/user/agents/analyst.md
#    scope: 모든 프로젝트에서 기본 후보로 사용
# 3. agent-crew 기본 analyst
#    path: ~/.agent-crew/system/agents/analyst.md
#    scope: agent-crew가 제공하는 기본값

crew:agent --agent-layer project analyst "분석해줘"       # 이번 한 번만 project agent 사용
crew:agent --save-agent-layer user analyst "분석해줘"     # 이 프로젝트에서 user agent를 계속 사용
```

## Agent visibility — always shown before spawning

In **explicit mode**:
```
[crew:agent] → analyst agent
              mode: explicit
              task: "explain the current domain model"
```

### Host bridge support

You can configure direct-agent auto-resume in one of two ways:

```text
AGENT_CREW_HOST_BRIDGE_COMMAND="your-host-bridge-command"
crew:agent --host-bridge-command "your-host-bridge-command" analyst "question"
```

When a bridge command is configured, the runtime invokes it immediately after
creating the handoff. The command is parsed into argv and executed without an
implicit shell; use `bash -c '...'` when shell features are required. A zero
exit status marks the request as:
`HOST_BRIDGE: auto_completed`.

In **auto-routing mode**:
```
[crew:agent] → historian
              reason: matched session-state Q pattern ("what ran")
              task: "what ran in this session?"
```

For a question/Q-shaped task that matches the session-state rule:
```
[crew:agent] → historian
              reason: matched session-state Q pattern ("어떤 에이전트")
              task: "방금 어떤 에이전트가 동작한거야?"
```

The visibility line is **mandatory** — it is always emitted before the agent
is invoked so the user always knows what is running.

### Auto-routing mode — agent selection only

When the user explicitly invokes `crew:agent` without an agent name,
conversational questions and implementation-shaped requests use the same
agent-selection table. This is agent selection only; it does not choose between
`crew:agent` and `crew:run`.

- Codebase Q ("explain how X works") → analyst (row 7)
- Session/git/project-state Q ("어떤 에이전트", "what just ran",
  "what's on this branch") → historian (row 6.5)

The top-level hook must not infer this command from ordinary natural language.

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
    crew:agent historian "…"  — Session / git / project state Q&A
    crew:agent issuer     "…"   — Issue publishing and work-item creation
    crew:agent mentor "…"    — Mentoring, coaching, concept teaching, growth feedback
    crew:agent learning-mentor "…" — Legacy concept-teaching alias; prefer mentor
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

3. If found and safe: resolve same-name agent definitions before Step 4.
```

Do not hard-code a restricted-agent list in this command. The restriction
information lives exclusively in `core/rules/agent-routing.md`.

When the same logical agent name exists in more than one layer, `crew:agent`
must not pick by fixed `project > user > system` precedence. It must show each
candidate with a friendly label, actual file path, scope meaning, description,
mtime, and short fingerprint, then stop with `STATUS: selection_required`.

`--agent-layer project|user|system` chooses one candidate for only the current
invocation. `--save-agent-layer project|user|system` writes
`.agent-crew/agent-resolution.json` in the project and continues. Saved
decisions are valid only while the selected file fingerprint still matches; a
changed file returns `AGENT_DECISION_STALE` and requires reconfirmation.

### Step 4 — Auto-route (auto-routing mode only)

Apply the **Auto-Routing Rules** from `core/rules/agent-routing.md`
top-to-bottom against the normalized TASK_STRING (case-insensitive). Rules
select an agent only; they do not decide whether the request should have been
`crew:agent` or `crew:run`:

```text
For each rule in priority order:
  If pattern matches TASK_STRING:
    AGENT_NAME  = rule target agent
    CONFIDENCE  = rule confidence
    ROUTE_REASON = rule reason text
    break.

If no rule matched (NONE):
  → Execute the Routing Failure Fallback procedure (see below).
  stop.
```

#### Routing Failure Fallback

When no auto-routing rule matches (NONE path above), the command MUST:

1. **Write gap telemetry** to `~/.agent-crew/state/{PROJECT_STATE_KEY}/routing-misses.log`
2. **Detect repeat patterns** by reading that log
3. **Present a structured choice UI** — never emit a plain-text error

##### Step 4a — Gap telemetry

Resolve `PROJECT_NAME` as display metadata and `PROJECT_STATE_KEY` as the
state identity from the current working directory or git root:

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --ensure \
  --migrate-legacy \
  --format shell)"
ROUTING_MISSES_LOG="${STATE_DIR}/routing-misses.log"
SESSION_ID="${CREW_SESSION_ID:-$(date -u +%Y%m%d-%H%M%S)}"
```

Append a JSONL record (one JSON object per line, no trailing comma, newline-terminated):

```python
import json, sys, os, re, datetime

routing_misses_log = os.path.expanduser(
    f"~/.agent-crew/state/{os.path.basename(os.getcwd())}/routing-misses.log"
)
os.makedirs(os.path.dirname(routing_misses_log), exist_ok=True)

record = {
    "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "query": TASK_STRING,
    "matched_candidates": [],   # empty — no rule matched
    "session_id": SESSION_ID,
}
with open(routing_misses_log, "a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

The log file is created on first write. If the directory or file cannot be written
(e.g., permissions), the failure is silently swallowed and the fallback continues.

##### Step 4b — Repeat-pattern detection

Before displaying the choice UI, count how many times the current query has failed
before. "Same query" is determined by a normalized form:

- lowercase
- strip leading/trailing whitespace
- collapse internal runs of whitespace to a single space
- strip common punctuation: `?!.,;:`

```python
import json, os, re

def normalize_query(q: str) -> str:
    q = q.lower().strip()
    q = re.sub(r"[?!.,;:]", "", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q

def count_prior_failures(routing_misses_log: str, current_query: str) -> int:
    """Count entries in routing-misses.log whose normalized query matches current_query.
    The current write in Step 4a is already appended, so subtract 1 to get prior count."""
    norm_current = normalize_query(current_query)
    try:
        with open(routing_misses_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return 0
    count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if normalize_query(rec.get("query", "")) == norm_current:
                count += 1
        except Exception:
            continue
    # Subtract 1 because the current failure was already appended in Step 4a
    return max(0, count - 1)

PRIOR_FAIL_COUNT = count_prior_failures(ROUTING_MISSES_LOG, TASK_STRING)
IS_REPEAT = PRIOR_FAIL_COUNT >= 3
```

`IS_REPEAT` is `True` when the same (normalized) query has failed to route
**3 or more times previously**. This threshold triggers the RECOMMENDED label on
option A.

##### Step 4c — Structured choice UI

Present a structured user-choice intent
(see `core/rules/capabilities/interactive-question.md`):

- **header**: "Routing Gap"
- **question**: Compose contextually:
  - If `IS_REPEAT` is `True`:
    ```
    No agent matched "{TASK_STRING}".
    This query pattern has failed to route {PRIOR_FAIL_COUNT} time(s) before.
    A new agent may be needed to handle this domain. Consider option A.
    ```
  - If `IS_REPEAT` is `False`:
    ```
    No agent matched "{TASK_STRING}". How would you like to proceed?
    ```
- **options**:
  - `[A] Delegate to crew:run` — Hand off as a full implementation task (supervisor + pipeline)
  - `[B] Specify agent explicitly` — I'll name the agent to use
  - `[C] Cancel` — Stop and rephrase
    (append " (Recommended)" to the label for option A when `IS_REPEAT` is `True`)

Codex conditional native behavior: when the current Codex session exposes
`request_user_input`, use it via the `askQuestion` mapping and persist the
choice with `crew question record` before proceeding.

Absence behavior (flag=false or no native surface in the current session): emit
the structured markdown question format:

```
No agent matched "{TASK_STRING}". How would you like to proceed?

[If IS_REPEAT] Note: This query pattern has failed to route {PRIOR_FAIL_COUNT} time(s) before.
A new agent may be needed to handle this domain.

Pick one (reply with the option number):

1. **Delegate to crew:run** — Hand off as a full implementation task (supervisor + pipeline)
2. **Specify agent explicitly** — I'll name the agent to use
3. **Cancel**
0. **cancel**
```

##### Step 4d — Handle the user's choice

**If [A] — Delegate to crew:run:**

```text
Invoke crew:run with TASK_STRING as the task description.
Pass the routing context as a note to the supervisor: "Routed from crew:agent
after no matching rule — treat as a full implementation task."
```

**If [B] — Specify agent explicitly:**

```text
Prompt the user: "Enter the agent name to use:"
Read the response as EXPLICIT_AGENT_NAME.
Re-invoke this command from Step 1 in explicit mode:
  AGENT_NAME  = EXPLICIT_AGENT_NAME
  TASK_STRING = (unchanged)
  (Jump to Step 3 — Validate agent)
```

**If [C] — Cancel:**

Stop silently.

**If cancel / no response:**

Stop silently. Do not emit an error message — the user dismissed the dialog.

##### Invariants for the fallback

- **NEVER emit a plain-text error message** for the no-match path. The structured
  choice UI is the only permitted output. Plain-text errors ("cannot auto-route
  this task") violate the approval prohibition enforced by Phase G6.
- **Gap telemetry is always written** before the UI is shown, even if the user
  cancels. The log is append-only and must not be truncated or deleted by this command.
- **Option A label** carries the "(Recommended)" tag **only** when `IS_REPEAT`
  is `True` (prior fail count >= 3). It must not appear on first or second failure.

---

## Escape hatch: host-native subagents

This section documents **when host-native subagents (Explore, Plan, and other
Claude Code built-in types) are officially permitted** and when they must route
through `crew:agent` instead.

### Permitted: read-only utility within an already-dispatched agent context

A host-native subagent MAY be used when ALL of the following conditions hold:

1. **Already inside a dispatched agent context** — the call is made from within
   an agent that was itself spawned by `crew:run` or `crew:agent` (i.e., the
   crew routing machinery has already fired for the outer task).
2. **Read-only codebase search** — the built-in subagent only reads files,
   searches symbols, or explores the repo. It does NOT write files, make commits,
   run deploy commands, or produce output that feeds directly into user-visible
   artifacts without review.
3. **No crew agent covers this specific capability** — the lookup is a pure
   host-native capability (e.g., an indexed symbol search or file-tree traversal)
   that no registered agent can fulfill more efficiently.

Example of a permitted bypass:

```text
# Inside a backend agent context (already crew-dispatched):
# Use host-native Explore to quickly find a symbol across a large codebase.
subagent_type="Explore"
prompt="Find all callers of UserService.cancelOrder"
```

This is acceptable because: the outer task was crew-routed, the Explore call
is read-only, and the result feeds back into the crew-dispatched agent's work
rather than producing independent user-visible output.

### Forbidden: direct use for crew-routable work

A host-native subagent MUST NOT be used when any of the following applies:

- **The task is crew-routable** — use `crew:agent` for direct single-agent work
  and `crew:run` for supervisor orchestration. Routing through a built-in
  subagent skips the agent registry, Routing Failure Fallback, and
  routing-misses.log telemetry entirely.
- **The task involves writing files or committing code** — file-write and commit
  operations must be performed by a registered crew agent whose own definition
  allows mutation, or by `crew:run` when supervisor gates are required.
- **The task is invoked from the top-level host context** — if there is no
  outer crew-dispatched agent, there is no routing context, and the call is
  a direct bypass of crew routing.
- **The task is conversational or user-facing** — Q&A, explanations, and
  design discussions must use `crew:agent analyst`, `crew:agent planner`,
  `crew:agent historian`, or `crew:agent mentor` as appropriate.

Forbidden example:

```text
# WRONG — using a built-in Plan subagent at the top level for a crew-routable task:
subagent_type="Plan"
prompt="Design the caching layer for the user-service API"
# Correct alternative: crew:agent planner "design the caching layer…"
```

### Decision table

| Context | Read-only search | Write/commit | Crew-routable task |
|---|---|---|---|
| Inside crew-dispatched agent | Permitted | Use selected crew agent rules | Use crew agent or crew:run |
| Top-level (no outer crew context) | Forbidden | Use crew:agent or crew:run | Use crew:agent or crew:run |

### Why this matters

When a built-in subagent runs outside crew routing:

- **Routing Failure Fallback never fires** — the user never sees the Routing Gap
  choice UI that would prompt creating a new agent for an unrecognized domain.
- **routing-misses.log is not updated** — the pattern-detection system that
  elevates routing gaps to new-agent suggestions receives no signal.
- **No visibility line is emitted** — the `[crew:agent] →` line that tells the
  user which agent is running is never shown.
- **No agent registry validation** — restricted agents (reviewer, devops,
  resolver) can be silently invoked, bypassing the supervisor's approval gate.

The permitted bypass above (read-only utility within an already-dispatched
agent) is the narrow case where these losses are acceptable because the outer
crew routing already fired and the inner call is purely mechanical.

---

### Step 5 — Raw input preservation

Preserve TASK_STRING verbatim as the direct-agent task. Do not translate it to
English, do not write a `normalized_task.md` artifact, and do not invoke a
normalizer agent or hook. Derived metadata such as `source_language` may be
recorded for display or routing diagnostics, but it must never replace the
raw task text consumed by the selected agent.

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

Invoke the agent using the host's native agent-call mechanism. Pass as the agent prompt:

```text
You are running in MODE=direct (lightweight invocation via crew:agent).

PROJECT_ROOT: {PROJECT_ROOT}
TASK: {TASK}

Work in PROJECT_ROOT. Complete the task and return your result. You may mutate
files or state only when the selected agent definition permits it. If the
selected agent declares a read-only contract, obey that contract strictly.

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
| Approval gate for destructive ops | Yes | Only when the selected agent implements it |
| Cost tracking | Yes (capability-gated) | No |
| Telemetry / progress events | Yes | Routing-gap only (routing-misses.log) |

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
   `~/.agent-crew/user/agents/`, or under the project-local
   `.agent-crew/project/agents/` layer.
2. Add a row to the **Agent Registry** in `core/rules/agent-routing.md`.
3. If auto-routing should reach it, add a row to the **Auto-Routing Rules**
   table in `core/rules/agent-routing.md`.
4. No changes to this file (`core/commands/agent.md`) are required.
