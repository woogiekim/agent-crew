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
- [Parallel-First Execution](#parallel-first-execution)
- [Real-Time Visibility](#real-time-visibility)
- [Centralized Approval Gate](#centralized-approval-gate)
- [crew:run Optimizations](#crewrun-optimizations)
- [Rules and Hooks](#rules-and-hooks)
- [Commands](#commands)
- [State Layout](#state-layout)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

When developing with an AI coding assistant, you typically have to manually direct each phase — requirements analysis, design, implementation, verification — and coordinate multiple agent roles consistently. This is tedious and error-prone.

**agent-crew** is an AI-assistant-agnostic workflow toolkit that automates this entire workflow. Install it once, and from any project you can invoke `crew:run` to automatically execute the full pipeline through a single unified execution engine.

The goal: let developers focus on *what* to build, while agent-crew handles requirements collection, analysis, planning, agent creation, handoffs, state management, quality validation, and pipeline orchestration automatically.

## Key Features

- **2-round deep requirements collection** — `crew:run` gathers scope, target, and constraints (Round 1), then domain-specific follow-ups (Round 2) before spawning supervisors; a fallback layer in supervisor Phase 1a repeats this if requirements were not passed in
- **Analyst reasoning layer** — Phase 1b invokes the analyst agent between requirements collection and planning; the analyst distills intent, identifies risks, and recommends the agent pipeline before the planner begins
- **Phase 1d plan approval gate** — after planning, supervisor displays the full implementation plan (pipeline stages, dynamic agents to create, risk summary) and requires explicit user approval via `AskUserQuestion` before any stage agent executes
- **Automatic subagent creation** — planner analyzes agent sufficiency and populates `needs_creation` in `pipeline.json`; supervisor Phase 1.5 spawns an inline Agent for each missing specialist that writes the agent definition directly to `~/.agent-crew/agents/{name}.md` before execution starts
- **Quality loop enforcement** — every implementation stage runs a validate → fix → re-validate cycle (maximum 3 retries) before reporting completion; a `BLOCKED` result halts the pipeline immediately
- **Parallel-first execution** — tasks are always run in parallel by default; file overlap is never a reason to serialize; the resolver agent handles post-parallel merge conflicts
- **Real-time progress visibility** — every phase and stage boundary emits a `[crew] TASK_ID | EVENT | detail` line and appends a timestamped entry to `{TASK_DIR}/progress.log`; `crew:status` reads this log to show a live pipeline snapshot at any time
- **Centralized approval gate** — stage agents (devops) never issue `AskUserQuestion` directly; they write a PLAN block and wait; the supervisor (N == 1) or `crew:run` orchestrator (N > 1) owns the single consolidated approval dialog
- **STOP Directive** — `auto-route.sh` injects `[agent-crew] STOP` when a development request is detected; the AI must call `crew:run` immediately with no preamble, no file reads, no Bash commands, and no clarifying questions
- **direct-edit-guard hook** — blocks `Edit` and `Write` tool calls to project source files when no active crew task marker exists, enforcing that all implementation goes through the pipeline
- **Reviewer always last** — every pipeline that produces implementation output ends with the `reviewer` agent, which verifies completeness against the PRD
- **Conditional deployment gate** — after all supervisors complete, `crew:run` always displays a per-task summary; deployment approval via `AskUserQuestion` fires only when the pipeline included a `devops` stage
- **Native sub-agent delegation** — orchestrator uses the host assistant's agent/delegation capability; no polling or signal files
- **Git worktree isolation** — each task runs in its own branch and worktree; merged back after completion
- **Project-clean state** — all state stored under `~/.agent-crew/state/{PROJECT_NAME}/`, never in your project directory
- **Global install** — one install works across all your projects
- **Provider-neutral capability framework** — every host-specific surface (task tools, background agents, monitor stream, hooks, structured questions, cost tracking) is gated by a flag in `capabilities.json` written by the active adapter (`claude`, `codex`, `generic`); core code never names a host-specific tool. See `core/rules/host-capabilities.md`.
- **Cost circuit breaker** — when the `cost_tracking` capability is advertised, the supervisor checks per-task token usage before every stage spawn and halts with `BLOCKER: cost_budget_exceeded` at 100% of the per-tier budget. Configure via `AGENT_CREW_BUDGET_DEEP|BALANCED|LIGHT`.
- **Opt-in stage timeout** — set `AGENT_CREW_STAGE_TIMEOUT_SECONDS=1800` to halt any stage that exceeds a wall-clock budget (mirrors the cost-breaker pattern; off by default).
- **Structured state files with schema validation** — `register.json` (per-task pointer state), `pipeline.json` (execution graph), `session.json` (multi-task registry), and `progress.buffer.jsonl` (one JSON event per line) all validate against JSON schemas under `core/schemas/` at supervisor Phase 0.
- **Pipeline telemetry** — `crew:telemetry` aggregates wall-clock duration, stage/retry counts, token totals, and blocker histograms across recent runs (read-only; works on every adapter).
- **Forbid plain-text approval** — when `hook_system` is advertised (Claude), a `PostToolUse[Agent]` validator blocks free-text yes/no prompts ("Shall I merge?" / "...진행할까요?") and feeds the violation back to the model. Hook script: `core/hooks/forbid-plaintext-approval.sh`.
- **Autonomous task injection** — when a session is already running and the user submits "추가로 해줘", "이것도 부탁해", "Also do...", "While you're at it..." etc., `crew:run` Step 1.5 auto-routes the new task into the live session without prompting.

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

# 4. Check live pipeline state for the current task
crew:status

# 5. Check cost summary
crew:cost
```

`crew:setup` runs `~/.agent-crew/setup/setup-host.sh`. That dispatcher is
provider-neutral: it calls adapter-owned `detect.sh` scripts and delegates to the
matching `setup.sh`. Host-specific detection, paths, and file formats live only
inside adapter implementations.

Set `AGENT_CREW_HOST` to an adapter directory name to override automatic host detection.

## How It Works

The orchestrator spawns or delegates to each sub-agent directly using the host AI tool's native mechanism. No daemon processes, no file polling, no signal files.

### Pipeline Flow

```
requirements → analyst → planner → [Phase 1d: plan approval] → [stages] → reviewer
```

For each task, the full execution path is:

```
crew:run "request"
       │
       ▼ Delegate to requirements agent (2-round AskUserQuestion interview)
       │   → merged into REQUIREMENTS block
[orchestrator]
       │
       ▼ delegate one supervisor per task (with REQUIREMENTS)
[supervisor]
       │ Phase 0:  Resume check + context bootstrap
       │ Phase 1a: REQUIREMENTS present → skip; absent → delegate to requirements agent
       │ Phase 1b: analyst (distill intent, identify risks, recommend pipeline)
       │ Phase 1c: planner (REQUIREMENTS + ANALYSIS → Case A path, skips AskUserQuestion)
       │ Phase 1d: AskUserQuestion — show plan, await Approve / Request changes / Cancel
       │ Phase 1.5: agent creation (needs_creation from pipeline.json)
       │ Phase 2:  stage execution with quality loop
       │ Phase 2.5: stage action gate (centralized approval for devops/deploy stages)
       ▼ Phase 3:  result reporting
[requirements] → [analyst] → [planner] → [approval gate] → [stage agents...] → [reviewer]
       │
       ▼ complete
[orchestrator] per-task Run Summary (always shown)
       │
       ▼ if pipeline included devops stage:
[orchestrator]   deployment plan displayed
[orchestrator]   AskUserQuestion → Approve / Cancel
       │ (Approve)
       ▼
[orchestrator] git push origin {branch}
```

### Multiple Tasks (Parallel)

```
crew:run "task A" | "task B" | "task C"
       │
       ▼ requirements agent for each task (2-round AskUserQuestion)
       │
       ▼ create git worktree + branch for each task
       │
       ▼ delegate all supervisors simultaneously (with per-task REQUIREMENTS)
[supervisor A]         ‖   [supervisor B]         ‖   [supervisor C]
  own worktree               own worktree               own worktree
  req→analyst→plan→[1d]→stages→reviewer   ...same...   ...same...
  local commits only         local commits only         local commits only
       │
       ▼ all complete
[orchestrator] per-task Run Summary (always shown)
       │
       ▼ if any pipeline included devops stage:
[orchestrator]   consolidated deployment plan (all branches)
[orchestrator]   single AskUserQuestion → Approve all / Cancel all
       │ (Approve)
       ▼
[orchestrator] git push origin for each branch
```

Each `supervisor` handles its full pipeline independently. **Remote push never happens inside supervisor** — the orchestrator pushes only after the user approves via `AskUserQuestion`.

### Supervisor Execution Phases

| Phase | Name | Description |
|---|---|---|
| **0** | Resume check + bootstrap | Path resolution, resume detection; if `pipeline.json` exists, jump directly to Phase 2 |
| **1a** | Requirement collection | Skip if REQUIREMENTS provided; else delegate to requirements agent (2-round AskUserQuestion interview) |
| **1b** | Analysis | Analyst agent — distill intent, identify ambiguities and risks, recommend agent pipeline; writes `{TASK_DIR}/context/analysis.md` |
| **1c** | Planning | Write active task marker; delegate to planner (REQUIREMENTS + ANALYSIS always present → Case A path, skips AskUserQuestion) |
| **1d** | Plan approval gate | Display full implementation plan (pipeline, dynamic agents, risk count); AskUserQuestion: Approve / Request changes / Cancel; "Request changes" re-invokes the planner and loops back to 1d |
| **1.5** | Dynamic agent creation | Read `needs_creation` from `pipeline.json`; spawn an inline Agent for each missing specialist; verify file exists before proceeding |
| **2** | Stage execution | Execute `stages` sequentially; apply quality loop rule (validate → fix → re-validate, up to 3 retries) per stage |
| **2.5** | Stage action gate | Display implementation summary; if pipeline includes `devops` stage, use AskUserQuestion for deployment approval before running devops; stage agents write PLAN blocks — they do not call AskUserQuestion directly |
| **3** | Result reporting | Collect git log; write `result.md`; emit `COMPLETED`; remove active marker (single mode) or preserve it (parallel mode) |

### Requirements Collection: 2-Round, 2-Layer Architecture

Requirements are collected in two layers to ensure the planner always receives structured input.

#### Layer 1 — Orchestrator (crew:run Step 5)

`crew:run` delegates to the requirements agent before spawning supervisors:

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

All answers are merged into a single `REQUIREMENTS` block passed to each supervisor.

#### Layer 2 — supervisor Phase 1a (fallback)

If a supervisor receives no `REQUIREMENTS` in its input (e.g., directly spawned without the orchestrator), it delegates to the **requirements agent** to run the same 2-round interview before invoking the analyst and planner. When `REQUIREMENTS` is present, Phase 1a is skipped entirely.

### State Directory Layout

```
~/.agent-crew/state/{PROJECT_NAME}/
├── capabilities.json          ← host capability flags (Phase A1)
├── session.json               ← multi-task session registry; runs > 1 day stale-filtered
├── cost/
│   └── {TASK_ID}.jsonl        ← per-call token usage (Phase 3.3, cost_tracking only)
└── tasks/
    ├── active                 ← marker file; present while a task is running
    └── {TASK_ID}/
        ├── register.json      ← per-task pointer state — current_phase, approval_status,
        │                         verification_status, modified_files, blocked_by (Phase F4)
        ├── pipeline.json      ← stages, needs_creation, completed_stages, host_task_ids
        ├── handoff.md         ← inter-agent context (written by analyst/planner)
        ├── result.md          ← final status written by supervisor
        ├── progress.log       ← real-time timestamped phase/stage events (human-readable)
        ├── progress.buffer.jsonl ← structured event buffer with trace_id (Phase F5)
        ├── archive/           ← paged-out handoff snapshots (Phase 3.5 documenter)
        └── context/
            ├── requirements.md ← collected requirements (written by requirements agent)
            ├── analysis.md    ← distilled intent, risks, recommended pipeline (written by analyst)
            ├── prd.md         ← PRD written by analyst/planner
            ├── action-plan.md ← planned destructive actions written by stage agents
            ├── approval.md    ← PLAN_READY / APPROVED / CANCELLED protocol file
            └── review.md      ← review report written by reviewer
```

All structured state files (`register.json`, `pipeline.json`, `session.json`,
`capabilities.json`, `progress.buffer.jsonl`) are validated against JSON
schemas under `core/schemas/` at supervisor Phase 0. Own-task files
hard-halt on schema violation; cross-task files warn but continue.
Per-file documentation lives under `core/rules/state-files/`.

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

supervisor Phase 1.5 reads this list and, for each entry, spawns an inline Agent
that writes the agent definition file directly to `~/.agent-crew/agents/{name}.md`.
This bypasses the `Skill` tool (which is unavailable inside sub-agents) and produces
the agent file using a standard template derived from the `name`, `reason`, and `role`
fields. After each invocation, Phase 1.5 verifies the file exists before continuing.
If an agent file still does not exist after the creation attempt, the pipeline halts
with `STATUS: BLOCKED`.

#### Custom Agent Dispatch (Phase 2)

When a `stages` entry contains a non-builtin agent name, supervisor Phase 2 resolves it at runtime:

1. Check if the name is a builtin: `planner`, `designer`, `frontend`, `backend`, `devops`, `resolver`, `reviewer`, `supervisor`
2. If **not builtin**: read `~/.agent-crew/agents/{name}.md` and prepend its full content to the stage prompt as a system preamble — the spawned Agent receives both the agent definition and the standard stage parameters (`TASK_DIR`, `PROJECT_ROOT`, `HANDOFF_PATH`, `QUALITY_RULE_PATH`)
3. If **builtin**: use the standard stage prompt format (the host already knows builtin agent definitions)

If the custom agent file does not exist at invocation time (e.g., Phase 1.5 was skipped or failed silently), Phase 2 reports `STATUS: BLOCKED` with the file path that was missing.

## Agents

| Agent | Role |
|---|---|
| **requirements** | Dedicated requirements collection — runs 2-round AskUserQuestion interview, validates scope, detects ambiguities, writes `requirements.md` |
| **analyst** | Reasoning and coordination layer — distills user intent, identifies risks and ambiguities, recommends agent pipeline; writes `analysis.md` |
| **planner** | PRD authoring, agent sufficiency evaluation, pipeline selection; writes `prd.md`, `pipeline.json`, `handoff.md` |
| **designer** | UI/UX spec design |
| **frontend** | UI implementation and verification |
| **backend** | Kotlin + Spring Boot, DDD design + TDD implementation |
| **devops** | CI/CD pipelines, infrastructure, containers, IaC; writes PLAN block and waits for approval before executing destructive actions |
| **reviewer** | Final stage — verifies implementation completeness against the PRD (read-only) |
| **resolver** | Automatic merge conflict resolution after parallel runs |
| **documenter** | Internal repo documentation — synthesizes `{TASK_DIR}/result.md`, drafts side-car README / CHANGELOG patches (opt-in via `--to-readme` for repo-tracked writes), and archives stage outputs to `{TASK_DIR}/archive/` |
| **learning-mentor** | Pedagogical teaching agent — runs 6-Phase structured tutoring sessions (assessment → concept foundation → application → critical evaluation → deepening → closing) with cognitive-load-controlled output |
| **supervisor** | Autonomous full-pipeline executor — the single execution engine behind `crew:run` |

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

The planner always follows Case A when invoked through the standard `crew:run` pipeline, because supervisor always includes both `REQUIREMENTS` and `ANALYSIS` in the planner prompt (Phase 1c).

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

Skills live under `core/agents/skills/` in the repository and are installed to
`~/.agent-crew/agents/skills/` by the installer.

## Parallel-First Execution

**Default to parallel execution. Never serialize tasks to avoid merge conflicts.**

When a request contains multiple independent sub-tasks — even if they touch the same files — run them as parallel supervisors:

```
crew:run "Sub-task A" | "Sub-task B" | "Sub-task C"
```

This is enforced at two levels:

- **`core/commands/run.md`** — the `crew:run` orchestrator always fans out to parallel supervisors for multiple tasks
- **`core/global-agents.md`** — the Parallel-First Execution Rule forbids serialization for conflict avoidance

### Why parallel is always correct for independent tasks

| Concern | Correct approach |
|---|---|
| Tasks touch the same files | Run in parallel — resolver handles post-merge conflicts |
| Tasks write to the same config file | Run in parallel — resolver merges the changes |
| One task depends on another's output | Run sequentially (true dependency) or as a single combined task |

Merge conflicts that arise after parallel completion are resolved by the **resolver agent** in `crew:run` Step 8. That is its explicit purpose. Choosing sequential execution to avoid conflicts sacrifices throughput for a problem the resolver already solves.

```bash
# Correct — parallel even if tasks touch the same files
crew:run "Fix bug A" | "Fix bug B"

# Wrong — serializing to avoid a conflict the resolver handles
crew:run "Fix bug A"   # then wait...
crew:run "Fix bug B"
```

## Real-Time Visibility

Every phase transition and stage boundary emits a progress event in two forms simultaneously.

### Inline emit format

Every supervisor prints a `[crew]`-prefixed line immediately before starting each phase or stage:

```
[crew] {TASK_ID} | {EVENT} | {detail}
```

Example output during a pipeline run:

```
[crew] 20260510-140000-0 | STARTED   | implement order management API
[crew] 20260510-140000-0 | PHASE     | 1a — Requirement collection
[crew] 20260510-140000-0 | PHASE     | 1b — Analysis
[crew] 20260510-140000-0 | PHASE     | 1c — Planning
[crew] 20260510-140000-0 | PHASE     | 1d — Plan approval
[crew] 20260510-140000-0 | STAGE     | 1/2 — backend
[crew] 20260510-140000-0 | STAGE_DONE| backend — N/A
[crew] 20260510-140000-0 | STAGE     | 2/2 — reviewer
[crew] 20260510-140000-0 | STAGE_DONE| reviewer — APPROVED
[crew] 20260510-140000-0 | COMPLETED | branch=feature/implement-order-api-20260510-140000-0 commits=3
```

In parallel runs (N > 1), each supervisor's `TASK_ID` prefix makes interleaved lines from concurrent runners distinguishable.

### progress.log file

In addition to inline text, every progress event is appended to a file-based log:

```
{TASK_DIR}/progress.log
```

Each entry is a timestamped line:

```
2026-05-10T14:22:01 | STARTED    | implement order management API
2026-05-10T14:22:03 | PHASE      | 1a — Requirement collection
2026-05-10T14:22:45 | PHASE      | 1b — Analysis
2026-05-10T14:23:10 | PHASE      | 1c — Planning
2026-05-10T14:23:11 | PHASE      | 1d — Plan approval
2026-05-10T14:24:00 | STAGE      | 1/3 — backend
2026-05-10T14:31:22 | STAGE_DONE | backend — N/A
2026-05-10T14:31:23 | COMPLETED  | branch=feature/implement-order-api-... commits=2
```

Because sub-agent inline output may be buffered until the agent completes, `progress.log` is the reliable source of truth for current pipeline state at any point during execution. `crew:status` reads this log to show a live snapshot.

### Event catalog

| EVENT | When emitted | Detail |
|---|---|---|
| `STARTED` | Phase 0 begins | task description (up to 60 chars) |
| `PHASE` | Each phase transition | phase name + short description |
| `STAGE` | Each pipeline stage begins | `{i}/{total} — {agent_name}` |
| `STAGE_DONE` | Each stage completes | `{agent_name} — {APPROVED\|NEEDS_CHANGES\|N/A}` |
| `BLOCKED` | Any BLOCKED result | blocker summary (1 line) |
| `RETRY` | Quality loop retry | `attempt {n} — {reason}` |
| `COMPLETED` | Phase 3 result written | `branch={BRANCH} commits={n}` |
| `COST_WARN` | Per-task token budget crosses 50% (Phase 3.3) | `{pct}% of budget ({total}/{budget} tokens)` |
| `COST_BLOCKED` | Per-task token budget hits 100% (Phase 3.3) | `task token budget exceeded` |
| `HANDOFF_PAGEOUT` / `HANDOFF_PAGEDOUT` | Documenter page-out for oversized `handoff.md` (Phase 3.5) | `size={chars} → archive/handoff-{N}.md` |
| `STATE_WARN` | F4 state-schema validator returned warnings at Phase 0 | `schema validator warnings (rc={n})` |
| `STAGE_TIMEOUT` | Per-stage wall-clock budget exceeded (Phase I11) | `stage {i} ({agent}) elapsed={n}s > budget={m}s` |

Every event is also written to `${TASK_DIR}/progress.buffer.jsonl` as a
single JSON object per line with `trace_id = {SESSION_ID}.{TASK_ID}.{STAGE_INDEX}.{RETRY_ATTEMPT}`
for cross-task correlation (Phase F5).

## Centralized Approval Gate

All approval decisions for destructive actions are owned exclusively by the orchestrator — never by stage agents directly.

### Stage agent responsibility

Stage agents that perform destructive operations (devops, and any agent that deploys, pushes, or merges) **must not issue `AskUserQuestion` directly**. Instead they:

1. Write their planned actions to `{TASK_DIR}/context/action-plan.md`
2. Return a `PLAN:` block to the supervisor:
   ```text
   PLAN:
     actions:
       - {command or action 1}
       - {command or action 2}
     risk: {none | low | medium | high}
     reversible: {yes | no}
   STATUS: plan_ready
   ```
3. Poll `{TASK_DIR}/context/approval.md` for `APPROVED` or `CANCELLED` (up to 60s, 5s interval)
4. Execute only after receiving `APPROVED`; halt with `STATUS: BLOCKED` on `CANCELLED` or timeout

### Orchestrator responsibility

| Mode | Who issues AskUserQuestion |
|---|---|
| N == 1 (single task) | supervisor (Phase 2.5) |
| N > 1 (parallel tasks) | crew:run orchestrator (Step 7.5) |

For N > 1, the orchestrator collects `action-plan.md` from every task and composes a **single consolidated AskUserQuestion** with the combined plan across all tasks.

### action-plan.md + approval.md protocol

```
stage agent              supervisor / orchestrator
──────────────────────   ──────────────────────────────────────
write action-plan.md
return PLAN: block  →    collect all PLAN blocks
poll approval.md         compose consolidated plan
                         issue single AskUserQuestion
                         write APPROVED/CANCELLED to approval.md
execute (if APPROVED) ←  
```

Plain-text approval requests ("Shall I?", "Should I?") are forbidden at every level. The `AskUserQuestion` structured UI is the only permitted approval method for deploy, push, merge, and destructive operations.

## crew:run Optimizations

Several optimizations reduce latency and context overhead across the pipeline:

- **Single-task worktree bypass** — when `N == 1`, `crew:run` skips `git worktree add` entirely and uses the current worktree directly with a plain `git checkout -b`. This eliminates worktree setup latency for the common single-task case.
- **Pre-created worktrees for parallel runs** — when `N > 1`, all worktrees are created before requirements collection begins so I/O-bound setup overlaps with user-facing interviews.
- **Context-loading discipline** — supervisor resolves all runtime paths once at startup (Phase 0) and passes only paths (never file contents) to sub-agents. Sub-agents read files directly. This keeps the supervisor's context slim throughout the pipeline.
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

If a stage reports `STATUS: BLOCKED`, the supervisor halts the pipeline immediately and writes the blocker detail to `{TASK_DIR}/result.md`. A blocked stage is never silently skipped.

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

### Forbid Plain-Text Approval (`core/hooks/forbid-plaintext-approval.sh`)

A `PostToolUse[Agent]` hook (Phase G6, gated on `hook_system=true`) that
inspects the agent's response for free-text yes/no approval prompts:

- English patterns: `Shall I ...?` / `Should I ...?` / `Do you want me to ...?`
  / `Would you like me to ...?` / `May I ...?` / `Can I [non-help] ...?`
- Korean patterns: `...할까요?` / `...해드릴까요?` / `...진행할까요?`
  / `...해도 될까요?` / `...해도 되나요?`

When a violation is detected the hook exits 2 with a stderr message
fed back to the model. The provider-neutral validator script
(`core/scripts/check-plaintext-approval.py`) is usable standalone for
diagnostic checks: `python3 ~/.agent-crew/scripts/check-plaintext-approval.py --text "..."`.

### Deployment Gate

After all supervisors finish, `crew:run` always displays a per-task Run Summary showing status, branch, commit count, and per-file before/after changes for each task.

Deployment approval via `AskUserQuestion` is triggered **only when the pipeline included a `devops` stage**. The full deployment plan is displayed first:

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

Pipelines that do not include a `devops` stage show the summary but skip the approval prompt entirely. `supervisor` never runs `git push` regardless — all remote operations are owned exclusively by the `crew:run` orchestrator.

## Commands

| Command | Description |
|---|---|
| `crew:setup` | Install the current host adapter and initialize the project workspace |
| `crew:run "task"` | Run a single task through the full pipeline |
| `crew:run "task A" \| "task B"` | Run multiple tasks in parallel |
| `crew:status` | Snapshot of the most recent task's pipeline state |
| `crew:cost` | Show the session cost summary |
| `crew:telemetry` | Pipeline timing, retry, and token aggregates across recent runs |
| `crew:agent-maker` | Design and register a custom agent |
| `crew:update` | Sync `~/.agent-crew/` with the source checkout |

### crew:status

`crew:status` reads `progress.log` and `pipeline.json` from the most recently active task and prints a live pipeline snapshot:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Task Status: 20260510-140000-0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task   : implement order management API
Branch : feature/implement-order-api-20260510-140000-0
Status : in-progress

Recent events (from progress.log):
  2026-05-10T14:22:01 | STARTED    | implement order management API
  2026-05-10T14:22:45 | PHASE      | 1b — Analysis
  2026-05-10T14:23:10 | PHASE      | 1c — Planning
  2026-05-10T14:23:11 | PHASE      | 1d — Plan approval
  2026-05-10T14:24:00 | STAGE      | 1/3 — backend

Pipeline stages:
  [✓] requirements
  [✓] analyst
  [✓] planner
  [▶] backend        ← current
  [ ] reviewer

Completed: 3 / 5 stages
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

`crew:status` is read-only and always targets the most recently modified task directory. It shows the "Recent events" section only when `progress.log` exists.

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
