# agent-crew

> AI assistant global toolkit — run a full multi-agent development pipeline from any project.

![License](https://img.shields.io/github/license/woogiekim/agent-crew)
![Platform](https://img.shields.io/badge/platform-AI%20Assistants-blue)

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Pipeline Decision Logic](#pipeline-decision-logic)
- [Agents](#agents)
- [Rules and Hooks](#rules-and-hooks)
- [State Layout](#state-layout)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

When developing with an AI coding assistant, you typically have to manually direct each phase — requirements analysis, design, implementation, verification — and coordinate multiple agent roles consistently. This is tedious and error-prone.

**agent-crew** is an AI-assistant-agnostic workflow toolkit that automates this entire workflow. Install it once, and from any project you can invoke `crew:run` to automatically execute the full pipeline through a single unified execution engine.

The goal: let developers focus on *what* to build, while agent-crew handles requirements collection, agent creation, handoffs, state management, quality validation, and pipeline orchestration automatically.

## Key Features

- **Requirements collection at the orchestrator level** — `crew:run` uses AskUserQuestion to gather scope, target users, and constraints before delegating to task-runners; answers are passed as a `REQUIREMENTS` block so the planner skips interactive prompts
- **Automatic subagent creation** — planner analyzes the request and populates `needs_creation` in `pipeline.json`; task-runner Phase 1.5 invokes `crew:agent-maker` for each missing specialist before execution starts
- **Quality loop enforcement** — every implementation stage runs a validate → fix → re-validate cycle (maximum 3 retries) before reporting completion; a `BLOCKED` result halts the pipeline immediately
- **STOP Directive** — `auto-route.sh` injects `[agent-crew] STOP` when a development request is detected; the AI must call `crew:run` immediately with no preamble or diagnostic output
- **direct-edit-guard hook** — blocks `Edit` and `Write` tool calls to project source files when no active crew task marker exists, enforcing that all implementation goes through the pipeline
- **Reviewer always last** — every pipeline that produces implementation output ends with the `reviewer` agent, which verifies completeness against the PRD
- **Deployment gate** — after all task-runners complete, `crew:run` displays a per-task summary and a full deployment plan, then requires `AskUserQuestion` approval before any `git push`
- **Native sub-agent delegation** — orchestrator uses the host assistant's agent/delegation capability; no polling or signal files
- **Git worktree isolation** — each task runs in its own branch and worktree; merged back after completion
- **Project-clean state** — all state stored under `~/.agent-crew/state/{PROJECT_NAME}/`, never in your project directory
- **Global install** — one install works across all your projects

## Installation

```bash
curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash
```

This installs the canonical workflow definitions, agents, hooks, rules, and status tools into `~/.agent-crew/`.
For Claude Code compatibility, the installer also places host-discoverable copies under `~/.claude/` by default. Set `AGENT_CREW_INSTALL_CLAUDE_COMPAT=0` to skip that compatibility layer.

Repository sources are organized by dependency direction:

| Path | Purpose |
|---|---|
| `core/commands`, `core/agents`, `core/hooks`, `core/rules`, `core/global-agents.md` | Provider-neutral canonical source |
| `core/setup/setup-host.sh` | Provider-neutral dispatcher that only detects the host and calls an adapter |
| `adapters/claude/setup.sh`, `adapters/codex/setup.sh`, `adapters/generic/setup.sh` | Host-specific installation outputs |
| Host-generated project artifacts | Generated compatibility outputs; not source of truth |

This repository does not track generated host output directories. They are created
by `crew:setup` and should remain uncommitted. Project-local generated artifacts are
registered in `.git/info/exclude` during setup so repository-level `.gitignore`
does not need host-specific directory names.

**After install, reload your shell:**
```bash
source ~/.zshrc   # zsh
source ~/.bashrc  # bash
```

## Quick Start

```bash
# 1. Initialize workspace once per project
crew:setup

# 2. Run a single task (crew:run collects requirements via AskUserQuestion first)
crew:run "implement order domain API with TDD"

# 3. Run multiple independent tasks in parallel
crew:run "implement order API" | "implement product API" | "implement user API"

# 4. Check cost summary
crew:cost
```

`crew:setup` runs `~/.agent-crew/setup/setup-host.sh`. That dispatcher is
provider-neutral: it calls adapter-owned `detect.sh` scripts and delegates to the
matching `setup.sh`. Host-specific detection, paths, and file formats live only
inside adapter implementations.

Set `AGENT_CREW_HOST` to an adapter directory name to override automatic host detection.

## How It Works

The orchestrator spawns or delegates to each sub-agent directly using the host AI tool's native mechanism. No daemon processes, no file polling, no signal files.

### Single Task

```
crew:run "request"
       │
       ▼ AskUserQuestion: scope / target / constraints → REQUIREMENTS block
[orchestrator]
       │
       ▼ delegate one task-runner (with REQUIREMENTS)
[task-runner]
       │ Phase 1: planner (REQUIREMENTS passed → skips AskUserQuestion)
       │ Phase 1.5: agent creation (needs_creation from pipeline.json)
       ▼ Phase 2: stage execution with quality loop
[planner] → [stage agents...] → [reviewer]
       │
       ▼ complete
[orchestrator] per-task summary
       │
       ▼ deployment plan displayed
[orchestrator] AskUserQuestion → Approve / Cancel
       │ (Approve)
       ▼
[orchestrator] git push origin {branch}
```

### Multiple Tasks

```
crew:run "task A" | "task B" | "task C"
       │
       ▼ AskUserQuestion for each task: scope / target / constraints
       │
       ▼ create git worktree + branch for each task
       │
       ▼ delegate all task-runners simultaneously (with per-task REQUIREMENTS)
[task-runner A]         ‖   [task-runner B]         ‖   [task-runner C]
  own worktree               own worktree               own worktree
  own context                own context                own context
  planner→stages→reviewer    planner→stages→reviewer    planner→stages→reviewer
  local commits only         local commits only         local commits only
       │
       ▼ all complete
[orchestrator] per-task summary (description, branch, commits, review status)
       │
       ▼ deployment plan displayed (branches + commits to be pushed)
[orchestrator] AskUserQuestion → Approve / Cancel
       │ (Approve)
       ▼
[orchestrator] git push origin for each branch
```

Each `task-runner` handles its full pipeline (planner → agent creation → stages → local commit). **Remote push never happens inside task-runner** — the orchestrator pushes only after the user approves the deployment plan via `AskUserQuestion`.

### Task-Runner Execution Phases

| Phase | What happens |
|---|---|
| **Phase 0** | Resume check — if `pipeline.json` exists, continue from `completed_stages` |
| **Phase 1** | Write active task marker; delegate to planner (with REQUIREMENTS if present) |
| **Phase 1.5** | Read `needs_creation` from `pipeline.json`; invoke `crew:agent-maker` for each missing agent |
| **Phase 2** | Execute `stages` sequentially; apply quality loop rule to every stage agent |
| **Phase 3** | Collect git log; write `result.md`; remove active marker (single mode) or preserve it (parallel mode) |

### State Directory Layout

```
~/.agent-crew/state/{PROJECT_NAME}/
└── tasks/
    ├── active                  ← marker file; present while a task is running
    └── {TASK_ID}/
        ├── pipeline.json       ← stages, needs_creation, completed_stages
        ├── handoff.md          ← inter-agent context (written by planner)
        ├── result.md           ← final status written by task-runner
        └── context/
            ├── prd.md          ← PRD written by planner
            └── review.md       ← review report written by reviewer
```

## Pipeline Decision Logic

The planner agent automatically selects which agents to run based on the collected requirements and request type:

| Request type | stages |
|---|---|
| Backend API / domain logic | `[["backend"], ["reviewer"]]` |
| Full-stack including UI | `[["designer", "backend"], ["frontend"], ["reviewer"]]` |
| UI only | `[["designer"], ["frontend"], ["reviewer"]]` |
| CI/CD, infrastructure, IaC | `[["devops"], ["reviewer"]]` |
| Backend + deployment | `[["backend"], ["devops"], ["reviewer"]]` |
| Full-stack + deployment | `[["designer", "backend"], ["frontend"], ["devops"], ["reviewer"]]` |
| Design / analysis only | `[]` |
| Custom agent role matched | custom agent in appropriate stage + `["reviewer"]` last |

`reviewer` is always the final stage for any pipeline that produces implementation output. It verifies completeness against the PRD and writes a report to `{TASK_DIR}/context/review.md`.

### Subagent Auto-Creation

When the planner determines that no existing agent can adequately fulfill a required role, it adds an entry to `needs_creation` in `pipeline.json`:

```json
{
  "needs_creation": [
    {
      "name": "example-specialist",
      "reason": "The generic backend agent cannot handle the domain-specific logic this task requires.",
      "role": "Performs X, handles Y edge cases, integrates with Z system."
    }
  ]
}
```

task-runner Phase 1.5 reads this list and invokes `crew:agent-maker` for each entry before executing any stage. If an agent file still does not exist after `crew:agent-maker` completes, the pipeline halts with `STATUS: BLOCKED`.

## Agents

| Agent | Role |
|---|---|
| **planner** | Requirements analysis, PRD writing, agent sufficiency evaluation, pipeline selection |
| **designer** | UI/UX spec design |
| **frontend** | UI implementation and verification |
| **backend** | Kotlin + Spring Boot, DDD design + TDD implementation |
| **devops** | CI/CD pipelines, infrastructure, containers, IaC |
| **reviewer** | Final stage — verifies implementation completeness against the PRD (read-only) |
| **resolver** | Automatic merge conflict resolution |
| **task-runner** | Autonomous full-pipeline executor — the single execution engine behind `crew:run` |

### Backend Agent Workflow (TDD Cycle)

```
DESIGN          → Domain model (Aggregate, Entity, Value Object, Domain Event)
IMPLEMENTATION  → RED: failing test → GREEN: minimal impl → REFACTOR
VERIFICATION    → OOP principles check + all tests GREEN → git commit
```

### Planner Agent Workflow

```
Step 1: Requirement collection
        ├─ REQUIREMENTS provided by orchestrator → use directly, skip AskUserQuestion
        └─ no REQUIREMENTS → call AskUserQuestion (scope / target / constraints)
Step 2: Write PRD to {TASK_DIR}/context/prd.md
Step 3: Agent capability analysis
        ├─ Discover built-in + custom agents
        ├─ Evaluate agent sufficiency per required role
        └─ Populate needs_creation for any role without an adequate agent
Step 4: Determine pipeline and write pipeline.json
Step 5: Write handoff.md
Step 6: Return concise completion report
```

## Rules and Hooks

### Quality Loop (`core/rules/quality-loop.md`)

Every implementation stage must run a validate → fix → re-validate cycle. The loop retries up to 3 times. A stage is complete only when all acceptance criteria pass:

- All PRD items for the stage are present in the output
- No obvious regressions
- Expected artifact files exist at their specified paths
- No TODOs, placeholders, or stubs in implementation output

If all 3 retries fail, the stage reports `STATUS: BLOCKED` with a `BLOCKER` detail, and the task-runner halts the pipeline.

### STOP Directive (`core/hooks/auto-route.sh`)

`auto-route.sh` is a `UserPromptSubmit` hook. When it detects a development request (backend, frontend, full-stack, file-level edits, project keywords), it injects `[agent-crew] STOP` into the system context.

When `[agent-crew] STOP` is present, the only permitted first action is to invoke `crew:run`. No explanation, no file reads, no Bash commands, no clarifying questions — call `crew:run` immediately.

### Direct-Edit Guard (`core/hooks/direct-edit-guard.sh`)

A `PreToolUse` hook that intercepts `Edit` and `Write` tool calls. If the target file is inside the project root and no `active` marker exists at `~/.agent-crew/state/{PROJECT_NAME}/tasks/active`, the call is blocked with:

```
[agent-crew] Direct edit blocked — no active crew task.
All implementation work must go through the crew pipeline: crew:run "your request"
```

Edits to `~/.agent-crew` and `~/.claude` paths are always allowed.

### Deployment Gate

After all task-runners finish, `crew:run` shows a per-task summary followed by a full deployment plan (branches, commit counts, commit log, risk notes). It then calls `AskUserQuestion` with two options:

- **Approve** — push all branches to origin now
- **Cancel** — hold; branches remain local for manual push later

`task-runner` never runs `git push`. All remote operations are owned exclusively by the `crew:run` orchestrator after explicit approval.

## State Layout

All state is stored outside your project directory:

```
~/.agent-crew/state/{PROJECT_NAME}/tasks/{TASK_ID}/
```

Your project directory only gains a `.crew_task_id` file during an active task (removed on completion). Git worktrees for parallel tasks are created under `.crew-worktrees/` inside the project root and removed after completion.

## Contributing

1. Fork this repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Commit your changes (`git commit -m 'feat: add your feature'`)
4. Push to the branch (`git push origin feat/your-feature`)
5. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE).
