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
- [State & Monitoring](#state--monitoring)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

When developing with Claude Code, you typically have to manually direct each phase — requirements analysis, design, implementation, verification — and coordinate multiple agent roles consistently. This is tedious and error-prone.

**agent-crew** is a Claude Code global plugin that automates this entire workflow. Install it once, and from any project you can run `/ship "what you want to build"` to automatically execute the full `planner → designer → frontend → backend` pipeline.

The goal: let developers focus on *what* to build, while agent-crew handles agent handoffs, state management, and pipeline orchestration automatically.

## Key Features

- **Automatic pipeline selection** — planner analyzes your request and picks only the agents needed
- **Daemon-centric event system** — agents emit events to `events.jsonl`; `crew-daemon` atomically updates `pipeline.json` (no race conditions, no direct state mutation by agents)
- **Git worktree isolation** — each task runs in its own branch and worktree; merged back to `feature/main` on completion
- **Real-time status panel** — `crew-status --live` monitors all projects' pipeline progress
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

# 2. Run the full pipeline
/ship "implement order domain API with TDD"

# Manual phase execution
/requirements
/design
/implement
/verify

# Status
/status
crew-status --live   # real-time monitor in a separate terminal
```

## How It Works

agent-crew uses a **daemon-centric event system**. Agents never mutate pipeline state directly — they only emit events. The `crew-daemon` process is the single source of truth for all state transitions.

```
/ship "request"
       │
       ▼
[Claude Code] sets up worktree + branch, writes pipeline.json (PENDING)
       │
       ▼ emit {"event": "PIPELINE_START"}
[events.jsonl]
       │
       ▼ crew-daemon reads event
[pipeline_update.py start]
  • status: PENDING → IN_PROGRESS
  • writes phase.txt, active_agent.txt
  • creates agent_signal/planner.ready
       │
       ▼ Claude Code detects planner.ready → activates as planner
[planner agent] analyzes request, writes PRD + handoff.md
       │
       ▼ emit {"event": "PHASE_COMPLETE", "agent": "planner"}
[events.jsonl]
       │
       ▼ crew-daemon reads event
[pipeline_update.py advance]
  • increments currentIndex
  • writes phase.txt, active_agent.txt
  • creates agent_signal/backend.ready  (or next agent)
       │
       ▼ Claude Code detects backend.ready → activates as backend
[backend agent] design → implement (TDD) → verify
       │
       ▼ emit {"event": "PHASE_COMPLETE", "agent": "backend"}
       │
       ▼ crew-daemon: PIPELINE_DONE → git merge → worktree cleanup
```

**Key invariant:** `pipeline.json`, `phase.txt`, and `active_agent.txt` are only ever written by `crew-daemon` (via `pipeline_update.py`). Agents write only to `events.jsonl`.

The one exception: agents may update `phase.txt` for *internal* sub-phase transitions (e.g., backend cycling through DESIGN → IMPLEMENTATION → VERIFICATION within its own lifecycle). Inter-agent transitions always go through the daemon.

### State directory layout

```
~/.claude/agent-crew/{PROJECT_NAME}/
├── config.json                 ← {"maxConcurrentTasks": 2}
├── orchestrator.pid
└── tasks/{TASK_ID}/
    ├── pipeline.json           ← managed by crew-daemon only
    ├── phase.txt               ← managed by crew-daemon (inter-agent)
    ├── active_agent.txt        ← managed by crew-daemon
    ├── branch.txt
    ├── worktree_path.txt
    ├── events.jsonl            ← append-only; agents write here
    ├── events.offset           ← daemon read cursor
    ├── agent_signal/           ← {agent}.ready trigger files
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

### Backend agent workflow (TDD cycle)

```
DESIGN       → Domain model (Aggregate, Entity, Value Object, Domain Event)
IMPLEMENTATION → RED: failing test → GREEN: minimal impl → REFACTOR
VERIFICATION → OOP principles check + all tests GREEN → git commit
```

## State & Monitoring

```bash
crew-status             # one-shot status for all projects
crew-status --live      # refresh every 2s
crew-status --live 5    # refresh every 5s
crew-daemon status      # check orchestrator daemon
crew-daemon stop        # stop daemon (kills all instances)
```

Example panel:
```
╔════════════════════════════════════════════════════════╗
║ agent-crew  projects: 2                                ║
╠════════════════════════════════════════════════════════╣
║   updated: 14:32:01                                    ║
╠════════════════════════════════════════════════════════╣
║ ▶ my-project                                           ║
║   Task   Implement order domain API with TDD           ║
║   Status IN_PROGRESS  phase: IMPLEMENTATION            ║
║   Agent  backend                                       ║
║   ✓planner → ▶backend                                  ║
║   Daemon ● RUNNING  pid:12345  events:3                ║
╠════════════════════════════════════════════════════════╣
║   other-project                                        ║
║   Task   -                                             ║
║   Status DONE  phase: DONE                             ║
║   Agent  planner                                       ║
║   ✓planner → ✓backend                                  ║
║   Daemon ● STOPPED  pid:-  events:5                    ║
╠════════════════════════════════════════════════════════╣
║   crew-status --live                                   ║
╚════════════════════════════════════════════════════════╝
```

## Contributing

1. Fork this repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Commit your changes (`git commit -m 'feat: add your feature'`)
4. Push to the branch (`git push origin feat/your-feature`)
5. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE).
