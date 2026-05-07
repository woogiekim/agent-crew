# agent-crew

> Claude Code global plugin — run a full multi-agent development pipeline with a single `/ship` command, from any project.

![License](https://img.shields.io/github/license/woogiekim/agent-crew)
![Platform](https://img.shields.io/badge/platform-Claude%20Code-blue)

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

When developing with Claude Code, you typically have to manually direct each phase — requirements analysis, design, implementation, verification — and coordinate multiple agent roles consistently. This is tedious and error-prone.

**agent-crew** is a Claude Code global plugin that automates this entire workflow. Install it once, and from any project you can run `/ship "what you want to build"` to automatically execute the full `planner → designer → frontend → backend` pipeline.

The goal: let developers focus on *what* to build, while agent-crew handles agent handoffs, state management, and pipeline orchestration automatically.

## Key Features

- **Automatic pipeline selection** — planner analyzes your request and picks only the agents needed
- **Native sub-agent spawning** — orchestrator uses Claude's Agent tool to spawn each sub-agent directly; no polling or signal files
- **Git worktree isolation** — each task runs in its own branch and worktree; merged back to `feature/main` on completion
- **Project-clean state** — all state stored under `~/.claude/agent-crew/{PROJECT_NAME}/`, never in your project directory
- **Global install** — one install works across all your projects

## Installation

```bash
curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash
```

This installs commands (`/setup`, `/ship`, etc.), agents, hooks, and status tools into `~/.claude/`.

**After install, reload your shell:**
```bash
source ~/.zshrc   # zsh
source ~/.bashrc  # bash
```

## Quick Start

```bash
# 1. Initialize workspace once per project
/setup

# 2. Run a single task
/ship "implement order domain API with TDD"

# 3. Run multiple independent tasks in parallel
/crew "implement order API" "implement product API" "implement user API"

# 4. Check cost summary
/cost
```

## How It Works

The orchestrator (Claude) spawns each sub-agent directly using the Agent tool. No daemon processes, no file polling, no signal files.

### Single task (`/ship`)

```
/ship "request"
       │
       ▼ Agent spawn
[planner] → prd.md + pipeline.json (stages) + handoff.md
       │
       ▼ stage 0: parallel spawn (single response, multiple Agent calls)
[designer] ‖ [backend] → independent result files
       │
       ▼ stage 1: spawn
[frontend] → UI implementation
       │
       ▼ complete
[orchestrator] final report
```

### Multiple tasks (`/crew`)

```
/crew "task A" "task B" "task C"
       │
       ▼ create git worktree + branch for each task
       │
       ▼ single response: spawn all task-runners simultaneously
[task-runner A]   ‖   [task-runner B]   ‖   [task-runner C]
  own worktree         own worktree         own worktree
  own context          own context          own context
  full pipeline        full pipeline        full pipeline
       │
       ▼ all complete
[orchestrator] merge guide
```

Each `task-runner` autonomously handles its full pipeline (planner → stages → commit), isolated in its own git worktree with a separate context window.

### State directory layout

```
~/.claude/agent-crew/{PROJECT_NAME}/
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
| **task-runner** | Autonomous full-pipeline executor — spawned by `/crew` for each task |

### Backend agent workflow (TDD cycle)

```
DESIGN       → Domain model (Aggregate, Entity, Value Object, Domain Event)
IMPLEMENTATION → RED: failing test → GREEN: minimal impl → REFACTOR
VERIFICATION → OOP principles check + all tests GREEN → git commit
```

## State Layout

All state is stored outside your project directory:

```
~/.claude/agent-crew/{PROJECT_NAME}/tasks/{TASK_ID}/
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
