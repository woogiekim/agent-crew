# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Agent Workflow Commands

```bash
/setup                           # Initialize current project workspace (run once)
/task "request"                  # Automatically execute full pipeline for a single task
/crew "TaskA" "TaskB" ...        # Execute multiple independent tasks in parallel
/cost                            # Show session cost summary
/agent-maker                     # Design and create a new agent
```

**`/task`** — The orchestrator directly spawns subagents using the Agent tool.  
Agents within the same stage are invoked simultaneously in a single response, enabling **parallel execution inside a stage**.

Example:

```text
full-stack → planner → [designer ‖ backend] → frontend
```

**`/crew`** — Executes multiple independent tasks in isolated git worktrees.  
Each task-runner autonomously executes its own full pipeline with completely isolated context.

Example:

```text
"Login API" ‖ "Product API" ‖ "Order API" → processed concurrently
```

## Absolute Rules

- Always write failing tests before implementing production code (backend agent)
- Never commit source code without tests
- Execute `/compact` immediately when context usage reaches 60%

## Build & Test Commands (Kotlin/Spring Boot Project)

```bash
./gradlew build
./gradlew test
./gradlew test --tests "TestClassName"
./gradlew test --tests "ClassName.methodName"
```

## Architecture Overview

**agent-crew**: Claude Code global plugin providing a multi-agent development workspace for all projects.

### Global Installation Structure

```text
~/.claude/
├── commands/                    ← Global commands (available in all projects)
│   ├── setup.md
│   ├── ship.md
│   ├── crew.md
│   ├── cost.md
│   └── agent-maker.md           ← New agent design & creation
└── agent-crew/
    ├── agents/                  ← Subagent definitions (flat .md with frontmatter)
    │   ├── planner.md           ← claude-sonnet-4-6
    │   ├── designer.md          ← claude-haiku-4-5
    │   ├── frontend.md          ← claude-sonnet-4-6
    │   ├── backend.md           ← claude-sonnet-4-6
    │   ├── resolver.md          ← claude-haiku-4-5
    │   ├── task-runner.md       ← claude-sonnet-4-6  (spawned by /crew)
    │   ├── {custom-agent}.md    ← Custom agent created by /agent-maker
    │   └── skills/              ← On-demand reference skills
    │       ├── tdd.md
    │       ├── ddd.md
    │       └── oop-principles.md
    └── {PROJECT_NAME}/          ← Project-specific state (auto-generated)
        └── tasks/
            └── {TASK_ID}/       ← Task-specific state (TASK_ID = YYYYmmdd-HHMMSS[-index])
                ├── pipeline.json    ← {"task": "...", "stages": [[...], [...]], "completed_stages": 0}
                ├── handoff.md       ← Agent handoff document
                ├── result.md        ← task-runner completion report (/crew only)
                └── context/
                    ├── prd.md
                    ├── design-spec.md
                    └── ...

{PROJECT_ROOT}/
└── .crew-worktrees/             ← Parallel task working directories (gitignored, auto-deleted after completion)
    ├── {TASK_ID_0}/             ← git worktree
    └── {TASK_ID_1}/
```

### Agent Composition

**Built-in Agents** (`~/.claude/agent-crew/agents/`):

| Agent | Role |
|------|------|
| planner | Requirement analysis, PRD creation, pipeline determination |
| designer | UI/UX specification creation |
| frontend | UI implementation and verification |
| backend | Kotlin + Spring Boot DDD/TDD implementation |
| resolver | Automatic merge conflict resolution |
| task-runner | Autonomous execution of full pipeline for a single task (spawned by `/crew`) |

**Custom Agents** (created with `/agent-maker`):

When a Subagent is created using `/agent-maker` and registered at `~/.claude/agent-crew/agents/<name>.md`:

- The planner can automatically discover and include it in pipeline stages
- `/ship` and `/crew` orchestrators can spawn it in the same way
- Custom agents operate as stages in the pipeline exactly like built-in agents

### Automatic Pipeline Determination

The `UserPromptSubmit` hook (`auto-route.sh`) detects natural-language keywords and automatically injects routing hints.  
Slash commands (`/task`, etc.) and question/explanation requests skip routing.

| Detection Condition | Pipeline |
|---------|---------|
| Full-stack keywords (`full-stack`, `system development`, etc.) | planner → [designer ‖ backend] → frontend |
| Frontend + backend keywords together | planner → [designer ‖ backend] → frontend |
| UI design keywords (`UX`, `wireframe`, `screen design`, etc.) | designer (→ frontend) |
| Frontend-only keywords (`UI`, `component`, `React`, etc.) | designer → frontend |
| Backend-only keywords (`API`, `domain`, `Entity`, `Spring`, etc.) | backend |

### Keyword Patterns (`auto-route.sh`)

- Backend: `API`, `backend`, `server`, `domain`, `Entity`, `Repository`, `Service`, `Kotlin`, `Spring`, `Controller`, `UseCase`
- Frontend: `UI`, `screen`, `component`, `React`, `Vue`, `Next`, `page`, `button`, `form`, `CSS`
- Full-stack: `full-stack`, `full development`, `service development`, `app development`
- UI Design: `UI design`, `screen design`, `UX`, `wireframe`
- Routing is skipped if no action verb exists: requires verbs such as `create`, `implement`, `develop`, `add`, etc.

### Skill Enforcement Mechanism

Claude Code has a system rule requiring skills to be invoked before execution when a skill matches.  
However, relying solely on Claude’s judgment may not guarantee compliance.

**The `auto-route.sh` hook enforces this behavior**:

- When development-request keywords are detected, a directive is injected through `hookSpecificOutput.additionalContext`
- Since it uses JSON instead of plain text, it is reliably inserted into Claude’s system context
- Message:

```text
⛔ Direct implementation prohibited — must execute skills/agents first
```

```text
# Claude memories/preferences alone cannot guarantee enforcement
# Only settings.json hooks can guarantee behavior
```

Slash commands (`/task`, `/crew`, etc.) and question/explanation requests are skipped.

### Context Management Principles

**Do not inline file contents** — directly embedding file content into agent prompts causes parent context accumulation at every stage.

Pass only the file path and let subagents read files directly.

```text
# Forbidden pattern (context explosion)
prompt: "--- handoff ---\n{entire handoff.md content}\n---"

# Correct pattern (context preservation)
prompt: "HANDOFF_PATH: {TASK_DIR}/handoff.md\nRead the handoff content directly from the file above."
```

### Context Flow (Ideal State)

| Level | Stored Information | Size |
|------|------------------|------|
| Orchestrator (`/task`) | Paths, state, stage completion status | Small |
| task-runner (`/crew`) | Paths, pipeline.json state | Small |
| Each subagent | Files it read + implementation | Medium (isolated) |

### Automated Hooks

| Hook | Trigger | Role |
|----|--------|------|
| `verify-rules.sh` | PostToolUse (Edit/Write, `.kt`/`.ts`/`.tsx`/`.js`) | Kotlin: excessive else/getter/test omission checks / TS: any/console/test omission checks |
| `guard-dangerous-commands.sh` | PreToolUse (Bash) | Blocks dangerous commands |
| `context-guard.sh` | PreToolUse (Agent) | Detects oversized agent prompts (2000+ chars or 500+ char code blocks) |

## Plugin Installation

```bash
# Install once (available for all projects)
/plugin marketplace add https://github.com/woogiekim/agent-crew
/plugin install agent-crew

# When starting a new project
/setup
/task "request details"
```