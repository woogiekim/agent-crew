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
- [State Layout](#state-layout)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

When developing with an AI coding assistant, you typically have to manually direct each phase — requirements analysis, design, implementation, verification — and coordinate multiple agent roles consistently. This is tedious and error-prone.

**agent-crew** is an AI-assistant-agnostic workflow toolkit that automates this entire workflow. Install it once, and from any project you can invoke the `run` workflow to automatically execute the full `planner -> designer -> frontend -> backend` pipeline.

The goal: let developers focus on *what* to build, while agent-crew handles agent handoffs, state management, and pipeline orchestration automatically.

## Key Features

- **Automatic pipeline selection** — planner analyzes your request and picks only the agents needed
- **Native sub-agent delegation** — orchestrator uses the host assistant's agent/delegation capability; no polling or signal files
- **Git worktree isolation** — each task runs in its own branch and worktree; merged back to `feature/main` on completion
- **Project-clean state** — all state stored under `~/.agent-crew/state/{PROJECT_NAME}/`, never in your project directory
- **Global install** — one install works across all your projects

## Installation

```bash
curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash
```

This installs the canonical workflow definitions, agents, hooks, and status tools into `~/.agent-crew/`.
For Claude Code compatibility, the installer also places host-discoverable copies under `~/.claude/` by default. Set `AGENT_CREW_INSTALL_CLAUDE_COMPAT=0` to skip that compatibility layer.

Repository sources are organized by dependency direction:

| Path | Purpose |
|---|---|
| `core/commands`, `core/agents`, `core/hooks`, `core/global-agents.md` | Provider-neutral canonical source |
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

# 2. Run a single task
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

Use plain `crew:<intent>` text in host UIs. In Codex, `@` is interpreted as
mention input rather than a custom command prefix.

## How It Works

The orchestrator spawns or delegates to each sub-agent directly using the host AI tool's native mechanism. No daemon processes, no file polling, no signal files.

### Single Task

```
crew:run "request"
       │
       ▼ delegate one task-runner
[task-runner]
       │
       ▼ planner + stage execution (local commits only — no push)
[planner] → [designer ‖ backend] → [frontend] → [reviewer]
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
       ▼ create git worktree + branch for each task
       │
       ▼ single response: delegate all task-runners simultaneously where supported
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

Each `task-runner` handles its full pipeline (planner → stages → local commit). **Remote push never happens inside task-runner** — the orchestrator pushes only after the user approves the deployment plan.

### State directory layout

```
~/.agent-crew/state/{PROJECT_NAME}/
└── tasks/{TASK_ID}/
    ├── pipeline.json
    ├── handoff.md
    ├── result.md
    └── context/
        ├── prd.md
        └── review.md
```

## Pipeline Decision Logic

The planner agent automatically selects which agents to run based on your request:

| Request type | Pipeline |
|---|---|
| Backend API / domain logic | planner → backend → reviewer |
| Full-stack app | planner → [designer ‖ backend] → frontend → reviewer |
| UI only | planner → designer → frontend → reviewer |
| Analysis / docs only | planner |

`reviewer` is always the final stage for any pipeline that produces implementation output. It verifies completeness against the PRD and writes a report to `{TASK_DIR}/context/review.md`.

After planner completes, you confirm the proposed pipeline before execution begins.

## Agents

| Agent | Role |
|---|---|
| **planner** | Requirements analysis, PRD writing, pipeline selection |
| **designer** | UI/UX spec design |
| **frontend** | UI implementation and verification |
| **backend** | Kotlin + Spring Boot, DDD design + TDD implementation |
| **reviewer** | Final stage — verifies implementation completeness against the PRD (read-only) |
| **resolver** | Automatic merge conflict resolution |
| **task-runner** | Autonomous full-pipeline executor — the single execution engine behind `crew:run` |

### Backend agent workflow (TDD cycle)

```
DESIGN       → Domain model (Aggregate, Entity, Value Object, Domain Event)
IMPLEMENTATION → RED: failing test → GREEN: minimal impl → REFACTOR
VERIFICATION → OOP principles check + all tests GREEN → git commit
```

## State Layout

All state is stored outside your project directory:

```
~/.agent-crew/state/{PROJECT_NAME}/tasks/{TASK_ID}/
```

Your project directory only gains a `.crew_task_id` file during an active task (removed on completion).

## Contributing

1. Fork this repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Commit your changes (`git commit -m 'feat: add your feature'`)
4. Push to the branch (`git push origin feat/your-feature`)
5. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE).
