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

**agent-crew** is an AI-assistant-agnostic workflow toolkit that automates this entire workflow. Install it once, and from any project you can invoke the `crew` workflow to automatically execute the full `planner → designer → frontend → backend` pipeline.

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
by `ac:setup` and should remain uncommitted. Project-local generated artifacts are
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
ac:setup

# 2. Run a single task
ac:crew "implement order domain API with TDD"

# 3. Run multiple independent tasks in parallel
ac:crew "implement order API" | "implement product API" | "implement user API"

# Compatibility alias
ac:task "implement order domain API with TDD"

# 4. Check cost summary
ac:cost
```

`ac:setup` runs `~/.agent-crew/setup/setup-host.sh`. That dispatcher is
provider-neutral: it calls adapter-owned `detect.sh` scripts and delegates to the
matching `setup.sh`. Host-specific detection, paths, and file formats live only
inside adapter implementations.

Set `AGENT_CREW_HOST` to an adapter directory name to override automatic host detection.

Adapters may expose more convenient syntax. For example, the Claude adapter can
also expose slash aliases, while the Codex adapter uses `ac:<intent>` text commands.

## How It Works

The orchestrator spawns or delegates to each sub-agent directly using the host AI tool's native mechanism. No daemon processes, no file polling, no signal files.

### Single Task

```
ac:crew "request"
       │
       ▼ delegate one task-runner
[task-runner]
       │
       ▼ planner + stage execution
[planner] → [designer ‖ backend] → [frontend]
       │
       ▼ complete
[orchestrator] final report
```

### Multiple Tasks

```
ac:crew "task A" | "task B" | "task C"
       │
       ▼ create git worktree + branch for each task
       │
       ▼ single response: delegate all task-runners simultaneously where supported
[task-runner A]   ‖   [task-runner B]   ‖   [task-runner C]
  own worktree         own worktree         own worktree
  own context          own context          own context
  full pipeline        full pipeline        full pipeline
       │
       ▼ all complete
[orchestrator] merge guide
```

Each `task-runner` autonomously handles its full pipeline (planner → stages → commit). A single task uses one task-runner; multiple tasks use one task-runner per task.

### State directory layout

```
~/.agent-crew/state/{PROJECT_NAME}/
└── tasks/{TASK_ID}/
    ├── pipeline.json
    ├── phase.txt
    ├── active_agent.txt
    ├── branch.txt
    ├── worktree_path.txt
    └── context/
        ├── session_handoff.md
        ├── prd.md
        └── design-spec.md
```

## Pipeline Decision Logic

The planner agent automatically selects which agents to run based on your request:

| Request type | Pipeline |
|---|---|
| Backend API / domain logic | planner → backend |
| Full-stack app | planner → designer → frontend → backend |
| UI only | planner → designer → frontend |
| Analysis / docs only | planner |

After planner completes, you confirm the proposed pipeline before execution begins.

## Agents

| Agent | Role |
|---|---|
| **planner** | Requirements analysis, PRD writing, pipeline selection |
| **designer** | UI/UX spec design |
| **frontend** | UI implementation and verification |
| **backend** | Kotlin + Spring Boot, DDD design + TDD implementation |
| **resolver** | Automatic merge conflict resolution |
| **task-runner** | Autonomous full-pipeline executor — the single execution engine behind `ac:crew` |

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
