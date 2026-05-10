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
- [Specialized Skills](#specialized-skills)
- [crew:run Optimizations](#crewrun-optimizations)
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

- **2-round deep requirements collection** — `crew:run` gathers scope, target, and constraints (Round 1), then domain-specific follow-ups (Round 2) before spawning task-runners; a fallback layer in task-runner Phase 1a repeats this if requirements were not passed in
- **Automatic subagent creation** — planner analyzes agent sufficiency and populates `needs_creation` in `pipeline.json`; task-runner Phase 1.5 spawns an inline Agent for each missing specialist that writes the agent definition directly to `~/.agent-crew/agents/{name}.md` before execution starts
- **Quality loop enforcement** — every implementation stage runs a validate → fix → re-validate cycle (maximum 3 retries) before reporting completion; a `BLOCKED` result halts the pipeline immediately
- **STOP Directive** — `auto-route.sh` injects `[agent-crew] STOP` when a development request is detected; the AI must call `crew:run` immediately with no preamble, no file reads, no Bash commands, and no clarifying questions
- **direct-edit-guard hook** — blocks `Edit` and `Write` tool calls to project source files when no active crew task marker exists, enforcing that all implementation goes through the pipeline
- **Reviewer always last** — every pipeline that produces implementation output ends with the `reviewer` agent, which verifies completeness against the PRD
- **Conditional deployment gate** — after all task-runners complete, `crew:run` always displays a per-task summary; deployment approval via `AskUserQuestion` fires only when the pipeline included a `devops` stage
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

# 2. Run a single task (crew:run collects requirements via 2-round AskUserQuestion first)
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
       ▼ Round 1 AskUserQuestion: scope / target / constraints
       ▼ Round 2 AskUserQuestion: domain-specific follow-up (database, auth, etc.)
       │   → merged into REQUIREMENTS block
[orchestrator]
       │
       ▼ delegate one task-runner (with REQUIREMENTS)
[task-runner]
       │ Phase 1a: REQUIREMENTS present → skip; absent → delegate to requirements agent
       │ Phase 1b: analyst (distill intent, identify risks, recommend pipeline)
       │ Phase 1c: planner (REQUIREMENTS + ANALYSIS passed → Case A path, skips AskUserQuestion)
       │ Phase 1.5: agent creation (needs_creation from pipeline.json)
       ▼ Phase 2: stage execution with quality loop
[requirements] → [analyst] → [planner] → [stage agents...] → [reviewer]
       │
       ▼ complete
[orchestrator] per-task summary (always shown)
       │
       ▼ if pipeline included devops stage:
[orchestrator]   deployment plan displayed
[orchestrator]   AskUserQuestion → Approve / Cancel
       │ (Approve)
       ▼
[orchestrator] git push origin {branch}
```

### Multiple Tasks

```
crew:run "task A" | "task B" | "task C"
       │
       ▼ Round 1 + Round 2 AskUserQuestion for each task
       │
       ▼ create git worktree + branch for each task
       │
       ▼ delegate all task-runners simultaneously (with per-task REQUIREMENTS)
[task-runner A]         ‖   [task-runner B]         ‖   [task-runner C]
  own worktree               own worktree               own worktree
  own context                own context                own context
  req→analyst→planner→stages→reviewer   req→analyst→planner→stages→reviewer   req→analyst→planner→stages→reviewer
  local commits only         local commits only         local commits only
       │
       ▼ all complete
[orchestrator] per-task summary (always shown)
       │
       ▼ if any pipeline included devops stage:
[orchestrator]   deployment plan (branches + commits to be pushed)
[orchestrator]   AskUserQuestion → Approve / Cancel
       │ (Approve)
       ▼
[orchestrator] git push origin for each branch
```

Each `task-runner` handles its full pipeline (requirements → analyst → planner → agent creation → stages → local commit). **Remote push never happens inside task-runner** — the orchestrator pushes only after the user approves the deployment plan via `AskUserQuestion`.

### Requirements Collection: 2-Round, 2-Layer Architecture

Requirements are collected in two layers to ensure the planner always receives structured input.

#### Layer 1 — Orchestrator (crew:run Steps 5)

`crew:run` always collects requirements before spawning task-runners:

**Round 1 — Base context (3 questions):**

| Question | Options |
|---|---|
| Scope | Backend API / Full-stack / UI only / Analysis only |
| Target | Internal tooling / End-user product / Developer tooling / Other |
| Constraints | Existing stack only / MVP / Performance / Security / No special constraints |

**Round 2 — Domain-specific follow-up (skipped for Analysis only):**

| Scope | Additional questions |
|---|---|
| Backend API | Database choice · Authentication method |
| Full-stack | State management approach · Database choice |
| UI only | State management approach · Design system |

All answers are merged into a single `REQUIREMENTS` block passed to each task-runner.

#### Layer 2 — task-runner Phase 1a (fallback)

If a task-runner receives no `REQUIREMENTS` in its input (e.g., directly spawned without the orchestrator), it delegates to the **requirements agent** to run the same 2-round interview before invoking the analyst and planner. When `REQUIREMENTS` is present, Phase 1a is skipped entirely.

### Task-Runner Execution Phases

| Phase | What happens |
|---|---|
| **Phase 0** | Resume check — if `pipeline.json` exists, continue from `completed_stages` |
| **Phase 1a** | Requirement collection gate — skip if REQUIREMENTS provided; else delegate to requirements agent (2-round AskUserQuestion interview) |
| **Phase 1b** | Analyst — distill intent, identify ambiguities and risks, recommend agent pipeline; writes `{TASK_DIR}/context/analysis.md` and returns ANALYSIS block |
| **Phase 1c** | Write active task marker; delegate to planner (REQUIREMENTS + ANALYSIS always present at this point → Case A path, skips AskUserQuestion) |
| **Phase 1.5** | Read `needs_creation` from `pipeline.json`; for each entry spawn an inline Agent that writes the agent definition to `~/.agent-crew/agents/{name}.md`; verify file exists before proceeding |
| **Phase 2** | Execute `stages` sequentially; apply quality loop rule to every stage agent |
| **Phase 2.5** | Display implementation summary; if pipeline includes `devops` stage, use AskUserQuestion for deployment approval before running devops |
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
            ├── requirements.md ← collected requirements (written by requirements agent)
            ├── analysis.md     ← distilled intent, risks, recommended pipeline (written by analyst)
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

task-runner Phase 1.5 reads this list and, for each entry, spawns an inline Agent
that writes the agent definition file directly to `~/.agent-crew/agents/{name}.md`.
This bypasses the `Skill` tool (which is unavailable inside sub-agents) and produces
the agent file using a standard template derived from the `name`, `reason`, and `role`
fields. After each invocation, Phase 1.5 verifies the file exists before continuing.
If an agent file still does not exist after the creation attempt, the pipeline halts
with `STATUS: BLOCKED`.

#### Custom Agent Dispatch (Phase 2)

When a `stages` entry contains a non-builtin agent name, task-runner Phase 2 resolves it at runtime:

1. Check if the name is a builtin: `planner`, `designer`, `frontend`, `backend`, `devops`, `resolver`, `reviewer`, `task-runner`
2. If **not builtin**: read `~/.agent-crew/agents/{name}.md` and prepend its full content to the stage prompt as a system preamble — the spawned Agent receives both the agent definition and the standard stage parameters (`TASK_DIR`, `PROJECT_ROOT`, `HANDOFF_PATH`, `QUALITY_RULE_PATH`)
3. If **builtin**: use the standard stage prompt format (the host already knows builtin agent definitions)

If the custom agent file does not exist at invocation time (e.g., Phase 1.5 was skipped or failed silently), Phase 2 reports `STATUS: BLOCKED` with the file path that was missing.

## Agents

| Agent | Role |
|---|---|
| **requirements** | Dedicated requirements collection — runs 2-round AskUserQuestion interview, validates scope, detects ambiguities, writes `requirements.md` |
| **analyst** | Reasoning and coordination layer — distills user intent, identifies risks, recommends agent pipeline; writes `analysis.md` |
| **planner** | PRD authoring, agent sufficiency evaluation, pipeline selection; writes `prd.md`, `pipeline.json`, `handoff.md` |
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
        ├─ Case A: REQUIREMENTS provided → use directly, skip AskUserQuestion
        └─ Case B: REQUIREMENTS absent → delegate to requirements agent
Step 2: Write PRD to {TASK_DIR}/context/prd.md
        └─ When ANALYSIS provided: use analysis.md risk table to populate PRD Risk section
Step 3: Agent capability analysis
        ├─ Discover built-in + custom agents
        ├─ Evaluate agent sufficiency per required role
        └─ Populate needs_creation for any role without an adequate agent
Step 4: Determine pipeline and write pipeline.json
        ├─ When ANALYSIS provided: use ANALYSIS.pipeline as starting point for stage composition
        └─ Pipeline Validation: enforce bidirectional needs_creation↔stages
           consistency (every needs_creation name must appear in stages; every
           non-builtin stage agent must have a needs_creation entry)
Step 5: Write handoff.md
Step 6: Return concise completion report
```

The planner always follows Case A when invoked through the standard `crew:run` pipeline, because task-runner always includes both `REQUIREMENTS` and `ANALYSIS` in the planner prompt (Phase 1c).

## Specialized Skills

Each agent loads a dedicated skill file on demand using the `Read` tool. Skills are never loaded at agent startup — only when the specific technique is needed during execution.

| Skill file | Loaded by |
|---|---|
| `core/agents/skills/requirement-gathering.md` | requirements, analyst |
| `core/agents/skills/pipeline-planning.md` | planner |
| `core/agents/skills/code-review.md` | reviewer |
| `core/agents/skills/conflict-resolution.md` | resolver |
| `core/agents/skills/tdd.md` | backend |
| `core/agents/skills/oop-principles.md` | backend |
| `core/agents/skills/api-design.md` | backend |
| `core/agents/skills/ui-component-design.md` | frontend |
| `core/agents/skills/ux-design.md` | designer |
| `core/agents/skills/deployment-ops.md` | devops |

## crew:run Optimizations

Several optimizations reduce latency and context overhead across the pipeline:

- **Single-task worktree bypass** — when `N == 1`, `crew:run` skips `git worktree add` entirely and uses the current worktree directly with a plain `git checkout -b`. This eliminates worktree setup latency for the common single-task case.
- **Pre-created worktrees for parallel runs** — when `N > 1`, all worktrees are created before requirements collection begins so I/O-bound setup overlaps with user-facing interviews.
- **Context-loading discipline** — task-runner resolves all runtime paths once at startup (Phase 0) and passes only paths (never file contents) to sub-agents. Sub-agents read files directly. This keeps the task-runner's context slim throughout the pipeline.
- **pipeline.json batching** — sequential (single-agent) stages use one combined `json.dump` call to update both `stage_agent_status` and `completed_stages`, halving write overhead versus parallel stages.
- **Slim agent creation templates** — Phase 1.5 uses a minimal agent template to reduce spawn latency when creating custom agents.
- **Skip-if-exists guard in Phase 1.5** — before spawning an agent creation sub-agent, Phase 1.5 checks whether the agent file already exists on disk and skips creation if it does.

## Rules and Hooks

### Quality Loop (`core/rules/quality-loop.md`)

Every implementation stage must run a validate → fix → re-validate cycle before it may report completion. The loop retries up to **3 times**. A stage is complete only when all acceptance criteria pass:

- All PRD items for the stage are present in the output
- No obvious regressions introduced
- Expected artifact files exist at their specified paths
- No TODOs, placeholders, or stubs in implementation output

The loop protocol for each stage:

```
1. Implement (or review) the assigned work.
2. Verify against all acceptance criteria.
3. If any criterion fails → fix the issue, return to step 2.
4. If all criteria pass → report STATUS: completed.
5. If retry limit reached without passing → report STATUS: BLOCKED with BLOCKER detail.
```

If a stage reports `STATUS: BLOCKED`, the task-runner halts the pipeline immediately and writes the blocker detail to `{TASK_DIR}/result.md`. A blocked stage is never silently skipped.

### STOP Directive (`core/hooks/auto-route.sh`)

`auto-route.sh` is a `UserPromptSubmit` hook. When it detects a development request (backend, frontend, full-stack, file-level edits, project keywords), it injects `[agent-crew] STOP` into the system context.

When `[agent-crew] STOP` is present, the **only permitted first action** is to invoke `crew:run`. All of the following are forbidden before `crew:run` is called:

- Producing any explanatory output
- Running Bash commands (including read-only or exploratory commands like `git status`, `ls`, `cat`)
- Reading files to understand the request
- Asking clarifying questions

The STOP directive is a hard override enforced both by `auto-route.sh` and by `core/global-agents.md`.

### Direct-Edit Guard (`core/hooks/direct-edit-guard.sh`)

A `PreToolUse` hook that intercepts `Edit` and `Write` tool calls. If the target file is inside the project root and no `active` marker exists at `~/.agent-crew/state/{PROJECT_NAME}/tasks/active`, the call is blocked with:

```
[agent-crew] Direct edit blocked — no active crew task.
All implementation work must go through the crew pipeline: crew:run "your request"
```

Edits to `~/.agent-crew` and `~/.claude` paths are always allowed (agent definitions and harness configuration).

### Deployment Gate

After all task-runners finish, `crew:run` always displays a per-task summary showing status, branch, commit count, and review result for each task.

Deployment approval via `AskUserQuestion` is triggered **only when the pipeline included a `devops` stage** (e.g., request type was Backend + deployment, CI/CD, or Full-stack + deployment). The full deployment plan is displayed first:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Deployment Plan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Branches to push:
  - {BRANCH}  ({N} commits)

Commits to be published:
  {git log --oneline}

Target remote: origin
Risk notes:
  - {merge conflicts detected?}
  - {blocked tasks?}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Two approval options are offered:

- **Approve** — push all branches to origin now
- **Cancel** — hold; branches remain local for manual push later

Pipelines that do not include a `devops` stage (e.g., Backend API only, UI only) show the summary but skip the approval prompt entirely. `task-runner` never runs `git push` regardless — all remote operations are owned exclusively by the `crew:run` orchestrator.

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
