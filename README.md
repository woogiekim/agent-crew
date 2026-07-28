# agent-crew

> Local orchestration/control layer for AI coding assistants — routing,
> state, handoffs, guardrails, audit, and adapter sync inside Codex/Claude
> prompt workflows.

![License](https://img.shields.io/github/license/woogiekim/agent-crew)
![Platform](https://img.shields.io/badge/platform-AI%20Assistants-blue)

## Table of Contents

- [Overview](#overview)
- [Foundational Direction](#foundational-direction)
- [Evaluation Artifacts](#evaluation-artifacts)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Testing](#testing)
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

When developing inside an AI coding assistant, you typically have to manually
direct each phase — requirements analysis, design, implementation, verification
— and coordinate multiple agent roles consistently. This is tedious and
error-prone.

**agent-crew** is an AI-assistant-agnostic orchestration layer that runs inside
host AI prompt workflows. It is not a replacement for Codex, Claude, Copilot, or
other execution platforms. The host AI remains the execution plane; agent-crew
provides the local control plane: routing, workflow intent, deterministic state
files, handoffs, guardrails, audit logs, update sync, and host adapters.
Comparisons to autonomous harnesses should be read at this layer only:
agent-crew coordinates prompt-runtime orchestration above the host AI; it does
not try to replace the host AI, own OS-level execution, or operate as an
independent commercial harness.

The best fit is a team or project that already uses AI coding assistants and
needs a durable workflow ledger: requirements, approvals, state transitions,
recovery steps, telemetry, and update evidence. agent-crew complements
productized harnesses and broad skill catalogs by focusing on governance,
auditability, and repeatable local control.

The goal: let developers focus on *what* to build, while agent-crew keeps the
AI-host workflow consistent and reproducible across requirements collection,
analysis, planning, agent creation, handoffs, state management, quality
validation, and pipeline orchestration.

Current validation conclusion: prompt handling has improved, especially around
STOP routing, handoff state, direct-agent boundaries, and memory support-path
latency. Native control-plane commands are now fast enough for routine use in
recent E2E probes; the remaining performance risk is host prompt-runtime latency
and project-specific agent execution overhead, which must continue to be
measured during commercialization validation.

## Foundational Direction

agent-crew is governed by permanent architectural direction documents that
define its identity as an AI Development Operating System and Persistent AI
Workforce System:

- [Foundational philosophy and operational constitution](docs/foundational-philosophy-and-operational-constitution.md)
- [Workflow-first architecture direction](docs/workflow-first-architecture-direction.md)
- [Persistent AI Workforce vision](docs/persistent-ai-workforce-vision.md)
- [Durable workflow architecture](docs/durable-workflow-architecture.md)
- [Persistent workflow test strategy](docs/persistent-workflow-test-strategy.md)

## Evaluation Artifacts

Use these artifacts to evaluate agent-crew on its own control-plane strengths:

- [Harness benchmark](docs/harness-benchmark-omc-ecc.md)
- [Timed scenario benchmark](docs/harness-scenario-benchmark.md)
- [Approval, recovery, and audit demo](docs/approval-recovery-audit-demo.md)
- [Hosted adapter validation evidence](docs/hosted-validation-evidence.md)

## Key Features

- **Requirements sufficiency gate** — well-specified tasks synthesize a `REQUIREMENTS` block inline through a deterministic helper script; ambiguous tasks still use the requirements agent for a structured interview before supervisors run; the same helper now reports interaction intensity, ambiguity score, and a default 20% ambiguity threshold for deep/strict workflows
- **Lean workflow methodology** — command files stay thin while shared rules define `Align -> Plan -> Execute/TDD -> Review`, context diet, workflow-origin vs target-scope handling, bounded reviewer loops, and fake-completion scanning. Standard-risk quality gates report concrete gaps and allow proceed / fix-gaps / strict-100 decisions when coverage is above threshold; high-risk gates remain strict.
- **Minimal-change decision gate** — analyst/planner output records Need Analyzer answers, ordered Capability Search, `Will Do`, `Will NOT Do`, and a diff budget in existing artifacts. The planning-time gate rejects implementation pipelines when reuse, configuration, deletion, existing APIs, or platform capabilities can satisfy the request first.
- **Explicit command adapter hook** — `auto-route.sh` adapts explicit agent-crew commands such as `$crew:run`, `$crew:agent`, `crew:run`, and `crew:agent`. It does not classify ordinary natural language as read-only or mutating, and it does not choose `crew:agent` vs `crew:run`.
- **Merged analyst + planner layer** — supervisor Phase 1b+1c invokes the analyst as the combined analysis/planning step; it distills intent, writes the PRD, chooses stages, and produces `pipeline.json` / `handoff.md`
- **Phase 1d plan approval gate** — after analysis/planning, supervisor displays the full implementation plan (pipeline stages, dynamic agents to create, risk summary) and requires explicit user approval before any stage agent executes
- **Automatic subagent creation** — the merged analysis/planning step can populate `needs_creation` in `pipeline.json`; supervisor Phase 1.5 spawns an inline Agent for each missing specialist that writes the agent definition into the installed/user agent layer before execution starts
- **Quality loop enforcement (test-driven review, Issue #3)** — every implementation stage runs a validate → fix → re-validate cycle (max 3 retries) before reporting completion; the reviewer EXECUTES the project's discovered test runner (`pytest` / `npm test` / `gradle test` / `go test` / `cargo test` / `tox`) and rejects with `STATUS: REJECTED REASON=tests_failed` on non-zero exit, `tests_absent_for_code_change` when no runner exists for a code-touching diff, or `cross_process_path_mismatch` when a `*.sh` hook and a `*.py / *.ts / *.js` module disagree on filesystem path literals. The supervisor loops back to the most recent implementer within the existing Stage Retry Rule budget; planner opts out for docs-only stages via `requires_test_execution: false` on the reviewer-stage object. **A real test suite now exists in `tests/`** (see [Testing](#testing)) — the reviewer's runner-discovery on this repo finds `pytest` and exercises the Python, shell, and integration suites end-to-end
- **Parallel-first execution** — tasks are always run in parallel by default; file overlap is never a reason to serialize; the resolver agent handles post-parallel merge conflicts
- **Real-time progress visibility** — every phase and stage boundary emits a `[crew] TASK_ID | EVENT | detail` line and appends a timestamped entry to `{TASK_DIR}/progress.log`; the orchestrator also writes an initial handoff event before supervisor spawn, and `crew:status` surfaces stalled handoffs with remediation guidance
- **Centralized approval gate** — stage agents (devops) never issue `AskUserQuestion` directly; they write a PLAN block and wait; the supervisor (N == 1) or `crew:run` orchestrator (N > 1) owns the single consolidated approval dialog
- **Explicit execution boundary** — ordinary natural-language input does not start a workflow, task, agent, or hidden router. Users choose the command boundary explicitly with `crew:run`, `crew:agent`, `$crew:run`, `$crew:agent`, or another management command.
- **Agent-first skill dispatch** — implementation agents discover capability skills through agent-crew's canonical `system/skills` + `user/skills` layers. Skill frontmatter (`loaded_by`, `axis`, `detection`) selects applicable skills; same-name user skills override system defaults; duplicate resolution and unindexed user-skill gaps are reported as framework-computed `decision_context`, not as required proof artifacts.
- **Direct-agent mutation support** — `crew:agent` can run mutating single-agent work when the selected agent definition allows mutation. Agents that must remain read-only declare that contract in their own instructions.
- **Route directive guard** — when a host exposes Agent `PostToolUse` hooks, `route-directive-guard.sh` detects Agent responses that received a STOP/ROUTE route lock but answered inline instead of entering `crew:run` / `crew:agent`
- **direct-edit-guard hook** — blocks `Edit` and `Write` tool calls to project source files when no active crew task marker exists, enforcing that all implementation goes through the pipeline
- **Reviewer always last** — every pipeline that produces implementation output ends with the `reviewer` agent, which verifies completeness against the PRD
- **Conditional deployment gate** — after all supervisors complete, `crew:run` always displays a per-task summary; deployment approval via `AskUserQuestion` fires only when the pipeline included a `devops` stage
- **Native sub-agent delegation where available** — orchestrator uses the host assistant's agent/delegation capability when advertised; adapters without background/task APIs fall back to inline execution and file-based state
- **Git worktree isolation** — each task runs in its own branch and worktree; merged back after completion
- **Project-clean state** — all state stored under collision-safe `~/.agent-crew/state/{PROJECT_STATE_KEY}/`, never in your project directory
- **Global install** — one install works across all your projects
- **Provider-neutral capability framework** — every host-specific surface (task tools, background agents, monitor stream, hooks, structured questions, cost tracking) is gated by a flag in `capabilities.json` written by the active adapter (`claude`, `codex`, `generic`); core code never assumes unavailable host features. See `core/rules/host-capabilities.md`.
- **Cost circuit breaker** — when the `cost_tracking` capability is advertised, the supervisor checks per-task token usage before every stage spawn and halts with `BLOCKER: cost_budget_exceeded` at 100% of the per-tier budget. Host bridges also append measured token records when their CLI output exposes usage. Configure via `AGENT_CREW_BUDGET_DEEP|BALANCED|LIGHT`.
- **Opt-in stage timeout** — set `AGENT_CREW_STAGE_TIMEOUT_SECONDS=1800` to halt any stage that exceeds a wall-clock budget (mirrors the cost-breaker pattern; off by default).
- **Structured state files with schema validation** — `register.json` (per-task pointer state), `pipeline.json` (execution graph), `session.json` (multi-task registry), and `progress.buffer.jsonl` (one JSON event per line) all validate against JSON schemas under `core/schemas/` at supervisor Phase 0.
- **Pipeline telemetry** — `crew:telemetry` aggregates wall-clock duration, stage/retry counts, tool-event counts, token totals, and blocker histograms across recent runs (read-only; works on every adapter).
- **Traceable runtime events** — `tool-events.jsonl` records native tool calls keyed by `trace_id` with redacted action summaries, timestamps, exit/status, token-usage references, and failure class; `delegation.jsonl` records provider-neutral span lineage (`span_id`, `parent_span_id`, `agent_role`, `unit_id`, `delegated_by`) while host task DAGs remain mirrors of local state.
- **Forbid plain-text approval** — when `hook_system` is advertised (Claude), a `PostToolUse[Agent]` validator blocks free-text yes/no prompts ("Shall I merge?" / "...진행할까요?") and feeds the violation back to the model. Hook script: `core/hooks/forbid-plaintext-approval.sh`.
- **Native issue reporting** — installed hooks detect explicit agent-crew bug/error reports, failed `crew` Bash payloads, and unexpected supervisor infrastructure blockers, redact common secrets, deduplicate by fingerprint, and store a local report/outbox entry through `crew report auto`. GitHub publication is an optional backend via `crew report publish`. Hook script: `core/hooks/auto-issue-report.sh`; contract: `core/rules/auto-issue-reporting.md`.
- **Autonomous task injection** — when a session is already running and the user submits "추가로 해줘", "이것도 부탁해", "Also do...", "While you're at it..." etc., `crew:run` Step 1.5 auto-routes the new task into the live session without prompting.
- **Raw input + localized output** — Korean task descriptions and other non-English inputs are preserved verbatim in internal artifacts (`pipeline.json`, `register.json`, `handoff.md`, agent prompts). User-facing output follows the user's input language per `core/rules/output-language.md`. Structured status tokens (`STATUS: completed`, `REVIEW: APPROVED`, `PLAN:`) remain English as a parser invariant.

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
by `crew setup` / `crew:setup` and should remain uncommitted. Project-local generated artifacts are
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
crew setup

# 2. Run a single task in the host runtime
crew:run "implement order domain API with TDD"

# 3. Run multiple independent tasks in parallel
crew:run "implement order API" | "implement product API" | "implement user API"

# 4. Check local pipeline state from any shell
crew status
crew status --summary

# 5. Check cost summary from any shell
crew cost

# 6. Run framework readiness diagnostics
crew doctor
crew doctor --mode runtime
crew config dump --effective
crew readiness workload --output dist/readiness-workload.json
crew readiness gate --validation-report dist/phase-2-validation.json --workload-evidence dist/readiness-workload.json

# 7. Inspect a task trace or resume coordinates
crew trace --task-id 20260523-103403-0 --include-tools
crew resume --print 20260523-103403-0
crew resume 20260523-103403-0   # records RESUME_REQUESTED
```

`crew:<intent>` is prompt workflow notation for host AI conversations. The
native shell CLI uses space-separated commands such as `crew run` and
`crew agent`; use those forms when you are calling the local `crew` binary from
a terminal.

Slash-style commands are host-specific aliases only. Use them only in adapters
that explicitly register slash commands; otherwise use plain `crew:<intent>`
prompt notation or the native `crew <command>` shell form.

`crew setup` runs `~/.agent-crew/setup/setup-host.sh`. That dispatcher is
provider-neutral: it calls adapter-owned `detect.sh` scripts and delegates to the
matching `setup.sh`. Host-specific detection, paths, and file formats live only
inside adapter implementations.

`crew` is the native shell entrypoint. Today, `crew setup`, `crew status`,
`crew trace`, `crew cost`, `crew doctor`, `crew config`, `crew debug`, `crew resume`,
`crew update --local`, and the initial `crew run` / `crew agent` state
transitions are deterministic CLI paths. `crew run` writes task state and a
supervisor handoff; until the host AI prompt runtime completes that handoff,
non-fake-host runs end with `STATUS: blocked`. `crew agent` validates a
read-only direct-agent request and writes host handoff state; the host prompt
runtime still performs the analysis.

Set `AGENT_CREW_HOST` to an adapter directory name to override automatic host detection.

### Host Capability Caveat

`agent-crew` is capability-gated. The same command may take different execution
paths depending on the active host adapter:

- Claude adapters can advertise native hooks, structured questions, task tools,
  or cost tracking when those surfaces are available.
- Codex currently runs in guided prompt mode: it installs agent/skill/hook
  compatibility files, but its project
  `capabilities.json` may legitimately set `agent_background`, `task_tools`,
  `interactive_question`, `monitor_tool`, `cost_tracking`, and `hook_system` to
  `false`. In that mode, `crew:run` uses inline execution and markdown/file
  fallbacks instead of claiming native background sessions, unconditional native
  structured prompts, live monitor streams, or token-budget enforcement.
- Codex Plan mode can expose `request_user_input`; in that mode the Codex
  adapter maps provider-neutral `askQuestion(prompt, options[])` prompts to the
  native structured input surface and records the selected option with
  `crew question`. Default mode keeps the markdown fallback.
- Codex may still materialize project-local hook files and `hooks.json` as
  advisory prompt-workflow guardrails. Treat those as installed compatibility
  assets, not as enforced `hook_system=true` guarantees unless the active
  adapter writes that capability flag.
- `crew doctor` and `crew config dump --effective` report each capability as
  `runtime-enforced`, `conditional-native`, `policy-only`, or `unavailable`. A
  false capability is not unconditional operational support; it means
  agent-crew will use documented fallback behavior, a mode-dependent native
  surface, or report the feature as unavailable.

Always inspect `~/.agent-crew/state/{PROJECT_STATE_KEY}/capabilities.json` when
debugging host-specific behavior.

### Task-State Cleanup

Use `crew cleanup-state` to inspect stale active markers, supervisor-pending
sentinels, and blocked or repaired task-state retention. Dry-run is the default:
it lists planned archival moves without mutating state. `--apply` archives stale
marker/sentinel files under `archive/task-state-cleanup`; it does not delete
blocked or repaired task directories. Those task artifacts are retained as
diagnostic evidence (`result.md`, `register.json`, `pipeline.json`, progress,
and `context/`).

### Setup State Choices

When `crew setup` finds existing project state, the default action is to reset
task/runtime state while preserving `project-context/`. Operators can instead
cancel setup, archive `project-context/` before regenerating it, or perform a
full state reset. `crew update` never prompts for these choices and always
preserves project state.

### Host Bridge Troubleshooting

If tasks stop at `STATUS: blocked` with `host AI bridge has not completed this handoff`,
use the recovery SOP and lightweight diagnostics:

- `cat ${TASK_DIR}/result.md`
- `crew status --json --task-id ${TASK_ID}`
- `crew telemetry --format json --task-id ${TASK_ID}`
- `crew report auto --summary "host bridge blocker pattern"`
- `crew cleanup-host-bridge --dry-run`
- `crew cleanup-host-bridge --apply`

`TASK_ID` and `TASK_DIR` are printed in the `crew run` output.

For Codex native CLI handoffs, the adapter installs a concrete bridge command:

```bash
export AGENT_CREW_HOST_BRIDGE_COMMAND="${HOME}/.agent-crew/adapters/codex/bin/codex-host-bridge"
```

When the environment variable is unset, `crew run` / `crew agent` first checks
the active host process environment (Codex or Claude) and can discover the
matching installed adapter bridge automatically. The legacy project
`capabilities.json` host value is used only as a fallback for older installs
that do not expose active host markers. Setting the variable remains useful when
overriding the bridge command. The bridge receives the task, handoff, result,
project, and direct-agent request environment and resumes the existing handoff
in the host runtime. If no default or explicit bridge is available, agent-crew
keeps using the internal resumable `STATUS: handoff_ready` fallback.

Host bridge execution is bounded so a stalled host CLI cannot leave operators
waiting forever. Workflow bridge commands default to
`AGENT_CREW_BRIDGE_TIMEOUT_SECONDS=1800`; direct-agent bridge commands default
to `AGENT_CREW_DIRECT_AGENT_BRIDGE_TIMEOUT_SECONDS=60`. A timeout records
`host_bridge_failure_reason=bridge_timeout`,
`failure_class=host_bridge_timeout`, and keeps the handoff/request resumable.
Set either timeout to `0` only for deliberate unbounded debugging.

## Testing

The repository ships with a real test suite under `tests/` covering the Python
validators (`pytest`), the bash scripts in `core/scripts` / `core/setup` /
`core/hooks`, and end-to-end integration scenarios (SSOT mnemos roundtrip,
schema validity of every existing `pipeline.json`, status-render snippet, CLI
smokes).

```bash
make test               # all suites (python + shell + integration)
make test-python        # pytest tests/python/
make test-shell         # bash tests/shell/test_*.bash
make test-integration   # bash tests/integration/test_*.bash

# or the bare runner if `make` is unavailable
bash tests/run-all.sh
```

Requirements: Python 3.10+ with `pytest` importable by `python3`
(`python3 -m pip install --user pytest`). `tests/run-all.sh` uses `pytest`
from `$PATH` when available and falls back to `python3 -m pytest`. If pytest is
missing entirely, it skips the Python suite with an install hint and still runs
shell + integration suites.

The suite is hermetic — every test uses `tmp_path` (pytest) or `mktemp -d`
(bash) for isolation; it never touches `${HOME}/.agent-crew/` or the real
mnemos store. See `tests/README.md` for the layout, how to add new tests,
and known issues surfaced by the suite.

## How It Works

Inside a host prompt runtime, the orchestrator delegates to sub-agents using the
host AI tool's native mechanism where that host exposes one. The native `crew`
CLI remains the deterministic control plane: it writes state and handoff
artifacts, then waits for the host prompt workflow to complete the execution
contract.

### Pipeline Flow

```
requirements sufficiency → analyst+planner → [Phase 1d: plan approval] → [stages] → reviewer
```

For each task, the full execution path is:

```
crew:run "request"
       │
      ▼ Run deterministic requirements sufficiency check
      │   → synthesize REQUIREMENTS inline, or delegate to requirements agent if ambiguous
[orchestrator]
       │
       ▼ delegate one supervisor per task (with REQUIREMENTS)
[supervisor]
       │ Phase 0:  Resume check + context bootstrap
      │ Phase 1a: REQUIREMENTS present → skip; absent → sufficiency check / requirements agent
      │ Phase 1b+1c: analyst as merged analysis+planning step
      │ Phase 1d: AskUserQuestion — show plan, await Approve / Request changes / Cancel
       │ Phase 1.5: agent creation (needs_creation from pipeline.json)
       │ Phase 2:  stage execution with quality loop
       │ Phase 2.5: stage action gate (centralized approval for devops/deploy stages)
       ▼ Phase 3:  result reporting
[requirements] → [analyst+planner] → [approval gate] → [stage agents...] → [reviewer]
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
      ▼ requirements sufficiency check for each task; requirements agent only for ambiguous tasks
       │
       ▼ create git worktree + branch for each task
       │
       ▼ delegate all supervisors simultaneously (with per-task REQUIREMENTS)
[supervisor A]         ‖   [supervisor B]         ‖   [supervisor C]
  own worktree               own worktree               own worktree
  req→analyst+plan→[1d]→stages→reviewer   ...same...   ...same...
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
| **1a** | Requirement collection | Skip if REQUIREMENTS provided; else run the sufficiency check and delegate to requirements agent only when ambiguous |
| **1b+1c** | Analysis + planning | Analyst agent runs as the merged analyst+planner step; writes `analysis.md`, `prd.md`, `pipeline.json`, and `handoff.md` |
| **1d** | Plan approval gate | Display full implementation plan (pipeline, dynamic agents, risk count); AskUserQuestion: Approve / Request changes / Cancel; "Request changes" re-invokes the analyst planning step and loops back to 1d |
| **1.5** | Dynamic agent creation | Read `needs_creation` from `pipeline.json`; spawn an inline Agent for each missing specialist; verify file exists before proceeding |
| **2** | Stage execution | Execute `stages` sequentially; apply quality loop rule (validate → fix → re-validate, up to 3 retries) per stage |
| **2.5** | Stage action gate | Display implementation summary; if pipeline includes `devops` stage, use AskUserQuestion for deployment approval before running devops; stage agents write PLAN blocks — they do not call AskUserQuestion directly |
| **3** | Result reporting | Collect git log; write `result.md`; emit `COMPLETED`; remove active marker (single mode) or preserve it (parallel mode) |

### Requirements Collection: Sufficiency-Gated Architecture

Requirements are collected only when the task description is not specific enough
to plan safely. Both the orchestrator and supervisor use the same sufficiency
check before invoking the requirements agent. A missing question can therefore
be intentional: `SUFFICIENT` tasks synthesize a `REQUIREMENTS` block inline and
do not ask the user. `AMBIGUOUS` tasks must ask and wait through the host's
structured-question surface or the adapter's markdown fallback.

The gate also exposes an OMC-inspired interaction policy. `light` favors
ordinary direct answers for read-only question-shaped work, `balanced` preserves
the current single-round requirements behavior, `deep` escalates high-ambiguity
implementation work to a deep interview, and `strict` treats the default
`0.20` ambiguity threshold as the implementation gate. The policy is
deterministic and additive: existing `SUFFICIENT` / `AMBIGUOUS` status output is
unchanged, while JSON and synthesized `REQUIREMENTS` blocks include
`ambiguity`, `ambiguity_threshold`, `interaction_intensity`, and
`implementation_allowed`.

#### Layer 1 — Orchestrator (crew:run Step 5)

`crew:run` first runs `core/scripts/requirements-sufficiency.py` per task:

- `SUFFICIENT` — synthesize the `REQUIREMENTS` block inline and continue.
- `AMBIGUOUS` — delegate to the requirements agent for a structured interview.
- `deep_interview` policy action — run the requirements agent in
  `MODE=deep_interview` until the remaining ambiguity is at or below the
  configured threshold, or block before implementation.

When delegation is needed, the requirements agent asks:

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

The synthesized or collected answers are merged into a single `REQUIREMENTS` block passed to each supervisor.

#### Layer 2 — supervisor Phase 1a (fallback)

If a supervisor receives no `REQUIREMENTS` in its input (e.g., directly spawned without the orchestrator), it runs the same sufficiency check and delegates to the **requirements agent** only when the task is ambiguous. When `REQUIREMENTS` is present, Phase 1a is skipped entirely.

### State Directory Layout

```
~/.agent-crew/state/{PROJECT_STATE_KEY}/
├── project.json               ← display PROJECT_NAME, canonical PROJECT_ROOT, PROJECT_STATE_KEY
├── capabilities.json          ← host capability flags (Phase A1)
├── project-context/           ← durable project-level markdown context (preserved by default)
├── session.json               ← multi-task session registry; runs > 1 day stale-filtered
├── cost/
│   └── {TASK_ID}.jsonl        ← measured hook/host-bridge token usage
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

`PROJECT_NAME` remains display metadata from the project root basename. The
state directory uses `PROJECT_STATE_KEY={slug(PROJECT_NAME)}-{sha256(PROJECT_ROOT)[:10]}`
so projects with the same basename do not collide. Legacy
`~/.agent-crew/state/{PROJECT_NAME}/` legacy directories are migrated when setup/run
can identify that they belong to the current canonical project root.

All structured state files (`register.json`, `pipeline.json`, `session.json`,
`capabilities.json`, `progress.buffer.jsonl`) are validated against JSON
schemas under `core/schemas/` at supervisor Phase 0. Own-task files
hard-halt on schema violation; cross-task files warn but continue.
Per-file documentation lives under `core/rules/state-files/`.

## Pipeline Decision Logic

The merged analyst+planner step automatically selects which agents to run based on the collected or synthesized requirements and request type:

| Request type | stages |
|---|---|
| Backend API / domain logic | `[{ "agents": ["backend"], "tdd_parallel": true }, ["reviewer"]]` |
| Full-stack including UI | `[["designer"], { "agents": ["backend"], "tdd_parallel": true }, ["reviewer"], { "agents": ["frontend"], "tdd_parallel": true }, ["reviewer"]]` |
| UI only | `[["designer"], { "agents": ["frontend"], "tdd_parallel": true }, ["reviewer"]]` |
| CI/CD, infrastructure, IaC | `[["devops"], ["reviewer"]]` |
| Backend + deployment | `[{ "agents": ["backend"], "tdd_parallel": true }, ["reviewer"], ["devops"], ["reviewer"]]` |
| Full-stack + deployment | `[["designer"], { "agents": ["backend"], "tdd_parallel": true }, ["reviewer"], { "agents": ["frontend"], "tdd_parallel": true }, ["reviewer"], ["devops"], ["reviewer"]]` |
| Design / analysis only | `[]` |
| Custom agent role matched | custom agent in appropriate stage + `["reviewer"]` last |

`reviewer` is always the final stage for any pipeline that produces implementation output. It verifies completeness against the PRD and writes a report to `{TASK_DIR}/context/review.md`.

### Subagent Auto-Creation

When the merged analysis/planning step determines that no existing agent can adequately fulfill a required role, it adds an entry to `needs_creation` in `pipeline.json`:

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
that writes the agent definition file into the installed/user agent layer.
This bypasses the `Skill` tool (which is unavailable inside sub-agents) and produces
the agent file using a standard template derived from the `name`, `reason`, and `role`
fields. After each invocation, Phase 1.5 verifies the file exists before continuing.
If an agent file still does not exist after the creation attempt, the pipeline halts
with `STATUS: BLOCKED`.

#### Custom Agent Dispatch (Phase 2)

When a `stages` entry contains a non-builtin agent name, supervisor Phase 2 resolves it at runtime:

1. Check if the name is a builtin: `planner`, `designer`, `frontend`, `backend`, `devops`, `resolver`, `reviewer`, `supervisor`
2. If **not builtin**: read the installed/user agent definition for `{name}` and prepend its full content to the stage prompt as a system preamble — the spawned Agent receives both the agent definition and the standard stage parameters (`TASK_DIR`, `PROJECT_ROOT`, `HANDOFF_PATH`, `QUALITY_RULE_PATH`)
3. If **builtin**: use the standard stage prompt format (the host already knows builtin agent definitions)

If the custom agent file does not exist at invocation time (e.g., Phase 1.5 was skipped or failed silently), Phase 2 reports `STATUS: BLOCKED` with the file path that was missing.

## Agents

| Agent | Role |
|---|---|
| **requirements** | Dedicated requirements collection — runs 2-round AskUserQuestion interview, validates scope, detects ambiguities, writes `requirements.md` |
| **analyst** | Merged analysis/planning layer — distills user intent, identifies risks and ambiguities, writes `analysis.md`, `prd.md`, `pipeline.json`, and `handoff.md` |
| **planner** | Legacy/specialized PRD and pipeline planner retained for compatibility and targeted workflows |
| **designer** | UI/UX spec design |
| **frontend** | UI implementation and verification |
| **backend** | Kotlin + Spring Boot, DDD design + TDD implementation |
| **test-writer** | TDD partner — owns `context/test-checklist.md`, checklist review handoff, `context/test-case-mapping.md`, and `context/test-coverage.md` for domain behavior coverage |
| **devops** | CI/CD pipelines, infrastructure, containers, IaC; writes PLAN block and waits for approval before executing destructive actions |
| **reviewer** | Final stage — verifies implementation completeness, runs tests, and enforces 100% changed-surface coverage against the PRD (read-only) |
| **resolver** | Automatic merge conflict resolution after parallel runs |
| **documenter** | Internal repo documentation — synthesizes `{TASK_DIR}/result.md`, drafts side-car README / CHANGELOG patches (opt-in via `--to-readme` for repo-tracked writes), and archives stage outputs to `{TASK_DIR}/archive/` |
| **mentor** | Mentoring and coaching agent — handles concept teaching, growth feedback, engineering guidance, and 6-Phase structured tutoring sessions for learning requests |
| **learning-mentor** | Legacy alias for the mentor agent's structured concept-teaching mode |
| **supervisor** | Autonomous full-pipeline executor — the single execution engine behind `crew:run` |

### Documentation CI Contract

agent-crew treats CI as continuous integration of the shared model, not only as
code merge plus test execution. When a task changes public behavior, workflow
commands, setup/update/deploy flow, DDD language, architecture decisions, or
long-lived agent guidance, docs are part of the integration evidence.

Planner outputs must include a `doc_impact` entry that either sets
`documentation_ci_required: true` and names the tracked, side-car, or external
documentation targets, or records `doc_impact: none` with a reason. Reviewer
approval must reject missing documentation synchronization with
`REASON: documentation_ci_missing` when the implementation and docs diverge.

### Backend Agent Workflow (TDD Cycle)

```
DESIGN          → Domain model (Aggregate, Entity, Value Object, Domain Event)
IMPLEMENTATION  → RED: failing test → GREEN: minimal impl → REFACTOR
VERIFICATION    → OOP principles check + all tests GREEN → git commit
```

### Merged Analyst + Planner Workflow

```
Step 1: Consume REQUIREMENTS
        ├─ Case A: REQUIREMENTS provided → use directly
        └─ Case B: REQUIREMENTS absent → supervisor Phase 1a supplies it first
Step 2: Write analysis.md and prd.md under {TASK_DIR}/context/
Step 3: Agent capability analysis and pipeline selection
        ├─ Discover built-in + custom agents
        ├─ Evaluate agent sufficiency per required role
        └─ Populate needs_creation for any role without an adequate agent
Step 4: Determine pipeline and write pipeline.json
        └─ Pipeline Validation: enforce bidirectional needs_creation↔stages
           consistency (every needs_creation name must appear in stages; every
           non-builtin stage agent must have a needs_creation entry)
Step 5: Write handoff.md
Step 6: Return concise completion report
```

The standard `crew:run` path no longer performs a separate planner spawn after analyst. Supervisor Phase 1b+1c delegates once to the analyst, which produces both reasoning and planning artifacts.

## Specialized Skills

Agents load every base skill associated with the selected agent before
execution. Capability skills are discovered through
`core/scripts/review-profile-dispatch.py --agent <name>` and selected by
frontmatter metadata.

| Canonical layer | Purpose |
|---|---|
| `core/agents/skills/` | Source-controlled system skill definitions |
| `~/.agent-crew/system/skills/` | Installed system defaults, refreshed by setup/update |
| `~/.agent-crew/user/skills/` | User extensions and same-name overrides, never overwritten |
| `~/.agent-crew/skills/` | Unified discovery view, rebuilt from system + user with user-wins precedence |
| `~/.claude/agent-crew/skills/` | Claude agent-crew mirror |
| `~/.codex/agent-crew/skills/` | Codex agent-crew guide mirror; native Codex skills remain under `~/.codex/skills/` |

Capability skill files use metadata that connects them to agents:

```yaml
loaded_by: backend,frontend,reviewer
axis: code-cleanup
detection: cleanup|refactor|dead.code|unused
```

The dispatcher returns a capability report at
`{TASK_DIR}/context/capability-skills-<agent>.json` with matched paths,
same-name duplicate resolution, task-relevant unindexed user-skill gaps, and a
framework-computed `decision_context`. This report tells the agent what to load;
it does not create `skill-use.json` proof artifacts by itself. Real outcomes,
tests, diffs, reviews, and tool events remain the evidence that a skill was
applied. During current-session fallback repair, missing or incomplete
specialist dispatch, skill-load, capability handler, `skill-use`, and
`skill-plan` notes are recorded as advisory coverage gaps rather than
completion blockers. Unapproved external host/plugin skill loads remain a hard
policy blocker.

Quality-loop completion follows the same rule. The framework still requires TDD
and reviewer approval for production-code changes, but completion is judged
from provider-neutral runtime state (`pipeline.json`, `progress.buffer.jsonl`,
reviewer quality metrics, tests, diffs, reviews, and tool events) rather than
from newly manufactured proof files. When standard-risk coverage reaches the
threshold but remains below 100%, `quality-loop-check.py` reports the concrete
gaps inline and offers `proceed`, `fix-gaps`, or `strict-100` choices; it does
not require a separate Gap Report artifact.

User coding conventions follow the same evidence model. The framework provides
`memory convention` and task snapshots, but actual convention content is local
per installed user under `~/.agent-crew/cache/user-conventions` unless
overridden. Supervisors pass only `USER_CONVENTIONS_PATH` to agents; agents
apply the relevant conventions during real work, and reviewer validates concrete
changed-line violations without requiring convention-use proof files.

Reviewer re-reviews are also bounded. After a prior Must finding,
`verify-prior-must-only` is the default mode. A newly raised Must in that mode
must declare `NEW_MUST_CLASSIFICATION` plus first-party evidence; otherwise the
machine classifier returns `review_contract_invalid` and retries the reviewer
only, avoiding an implementation loop caused by reviewer slop.

`crew update` refreshes system skills, then rebuilds the unified discovery view
with user-wins precedence. A same-name file under `~/.agent-crew/user/skills/`
is preserved and will continue to override the refreshed system copy. Use
`crew update --reconcile-skills` to write comparison diffs under the project
state directory before hand-merging a user override.

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
[crew] 20260510-140000-0 | PHASE     | 1b+1c — Analysis + Planning
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
2026-05-10T14:22:45 | PHASE      | 1b+1c — Analysis + Planning
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

The shell guard for dangerous commands is a workflow-integrity check, not an OS
sandbox. When an approved orchestrator path needs to run `git push`, `git
merge`, or deployment commands, it must write a one-shot JSON approval to
`~/.agent-crew/approvals/dangerous-commands.approved` with the exact `kind`,
`command`, and a short-lived `expires_at` timestamp. The guard consumes that
marker after one matching command and audits both blocks and allows to
`~/.agent-crew/audit/dangerous-commands.jsonl`.

## crew:run Optimizations

Several optimizations reduce latency and context overhead across the pipeline:

- **Single-task worktree bypass** — when `N == 1`, `crew:run` skips `git worktree add` entirely and uses the current worktree directly with a plain `git checkout -b`. This eliminates worktree setup latency for the common single-task case.
- **Pre-created worktrees for parallel runs** — when `N > 1`, all worktrees are created before requirements collection begins so I/O-bound setup overlaps with user-facing interviews.
- **Context-loading discipline** — supervisor resolves all runtime paths once at startup (Phase 0) and passes only paths (never file contents) to sub-agents. Sub-agents read files directly. This keeps the supervisor's context slim throughout the pipeline.
- **pipeline.json batching** — sequential (single-agent) stages use one combined `json.dump` call to update both `stage_agent_status` and `completed_stages`, halving write overhead versus parallel stages.
- **Slim agent creation templates** — Phase 1.5 uses a minimal agent template to reduce spawn latency when creating custom agents.
- **Skip-if-exists guard in Phase 1.5** — before spawning an agent creation sub-agent, Phase 1.5 checks whether the agent file already exists on disk and skips creation if it does.
- **Stable mnemos recall fast path** — `~/.agent-crew/bin/memory search` first uses mnemos's advertised `search --fast --json` capability, then falls back through documented compatibility paths. The stable provider contract is documented in `docs/memory-provider-contract.md`; the legacy direct FTS fallback is deprecated and guarded by compatibility tests.
- **Local support-memory capture/read contract** — agent-crew support captures default to mnemos's local `default` backend unless `MNEMOS_BACKEND` is explicitly set, and support reads use the same default backend. This keeps end-of-stage memory writes fast and immediately readable by hooks while preserving an opt-in path for users who want every support capture synced through their configured mnemos backend.
- **Task-scoped user convention snapshots** — `memory convention snapshot` reads the installed user's local convention cache once per task and writes `{TASK_DIR}/context/user-conventions.snapshot.json`. Later stages reuse the frozen owner/project snapshot and receive only a stage-filtered digest path, avoiding repeated convention searches or prompt-inlined convention text.
- **Sub-second mnemos process polling** — the bounded mnemos wrapper polls at 0.1s by default instead of adding a full one-second floor to every fast memory command.

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

### Agent-Crew Routing Directives (`core/hooks/auto-route.sh`)

`auto-route.sh` is a `UserPromptSubmit` hook, but it is not a natural-language
router. It adapts only explicit agent-crew command syntax and otherwise emits no
STOP/ROUTE directive. This keeps execution intent explicit: the user chooses
`crew:run` vs `crew:agent` by command.

Codex `$crew:*` wrapper commands are treated as explicit workflow invocations
when they appear at the beginning of the prompt. For example, `$crew:run 코드리뷰`
means run the `코드리뷰` task through `crew:run`; it is not a request to review
the `crew:run` skill. To review the wrapper itself, explicitly target the skill,
wrapper, file, or `SKILL.md` in the prompt, such as `` `$crew:run` skill review ``.

Machine-control replies used by structured-choice fallbacks, such as a bare
option number, still pass through without starting execution.

`route-directive-guard.sh` remains for compatibility with already-loaded or
external contexts that contain a `[agent-crew] STOP` or `[agent-crew] ROUTE`
directive, but the current auto-route hook no longer creates those directives
from ordinary natural language.

#### Codex current-session update limitation

`crew update` refreshes installed files on disk, including hooks, commands,
rules, generated agents, and Codex skill mirrors. It cannot retroactively replace
system/developer context that is already loaded into an active Codex
conversation. After changing routing policy, start a new Codex session for the
new instructions to apply automatically. In the old session, explicitly invoke
`$crew:run` or `$crew:agent`.

### Direct-Edit Guard (`core/hooks/direct-edit-guard.sh`)

A `PreToolUse` hook that intercepts `Edit` and `Write` tool calls. If the target file is inside the project root and no `active` marker exists at `~/.agent-crew/state/{PROJECT_STATE_KEY}/tasks/active`, the call is blocked with:

```
[agent-crew] Direct edit blocked — no active crew task.
All implementation work must go through the crew pipeline: crew:run "your request"
```

Edits to `~/.agent-crew` and `~/.claude` paths are always allowed (agent definitions and adapter configuration).

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
## Deployment Plan

Branches to push:
  - {BRANCH}  ({N} commits)

Commits to be published:
  {git log --oneline}

Target remote: origin
Risk notes:
  - {merge conflicts detected?}
  - {blocked tasks?}
```

Two approval options are offered:

- **Approve** — push all branches to origin now
- **Cancel** — hold; branches remain local for manual push later

Pipelines that do not include a `devops` stage show the summary but skip the approval prompt entirely. `supervisor` never runs `git push` regardless — all remote operations are owned exclusively by the `crew:run` orchestrator.

## Commands

| Command | Description |
|---|---|
| `crew setup` | Native shell command: install the current host adapter and initialize the project workspace |
| `crew status` | Native shell command: deterministic snapshot of local task state |
| `crew status --summary` | Native shell command: compact operator view with counts, bridge state, next action, and JSON/detail pointers |
| `crew trace` | Native shell command: read-only progress trace from `progress.buffer.jsonl` or `progress.log` |
| `crew cost` | Native shell command: token/cost aggregates from local cost JSONL state |
| `crew doctor` | Native shell command: split operational checks via `--mode static`, `--mode runtime`, `--mode host`, or `--mode all` |
| `crew config doctor` | Native shell command: runtime config visibility checks |
| `crew config dump --effective` | Native shell command: capability flags, active adapter, budgets, timeouts, report settings, memory backend, state directory, and install drift |
| `crew debug` | Native shell command: combined read-only doctor, telemetry, and cost snapshot |
| `crew readiness gate` | Native shell command: default-threshold readiness gate with blocker reporting |
| `crew readiness workload` | Native shell command: deterministic temporary host-bridge workload evidence generator |
| `crew resume [TASK_ID]` | Native shell command: request host-runtime continuation and record `RESUME_REQUESTED`; use `--print` or `--dry-run` for read-only coordinates |
| `crew update --local [SOURCE]` | Native shell command: sync `~/.agent-crew/` with a source checkout |
| `crew run "task"` | Native shell command: create deterministic task state and supervisor handoff; currently blocks until a host AI prompt runtime completes the handoff |
| `crew agent ...` | Native shell command: validate a read-only direct-agent request and write host handoff state |
| `crew:setup` | Host prompt alias for setup in adapters that expose it |
| `crew:run "task"` | Run a single task through the full pipeline |
| `crew:run "task A" \| "task B"` | Run multiple tasks in parallel |
| `crew:status` | Snapshot of the most recent task's pipeline state |
| `crew:cost` | Show the session cost summary |
| `crew:telemetry` | Pipeline timing, retry, and token aggregates across recent runs |
| `crew:agent-maker` | Design and register a custom agent or agent-crew skill |
| `crew:update` | Sync `~/.agent-crew/` with the source checkout |

### crew:status

`crew:status` reads local task state from the most recent task directories and prints a live pipeline snapshot:

```
## Task Status: 20260510-140000-0

Task   : implement order management API
Branch : feature/implement-order-api-20260510-140000-0
Status : in-progress

Recent events (from progress.log):
  2026-05-10T14:22:01 | STARTED    | implement order management API
  2026-05-10T14:22:45 | PHASE      | 1b+1c — Analysis + Planning
  2026-05-10T14:23:11 | PHASE      | 1d — Plan approval
  2026-05-10T14:24:00 | STAGE      | 1/3 — backend

Pipeline stages:
  [✓] requirements
  [✓] analyst
  [✓] planner
  [▶] backend        ← current
  [ ] reviewer

Completed: 3 / 5 stages
```

`crew:status` is read-only. When a task has been created but the supervisor has not produced progress artifacts, status reports a stalled supervisor handoff instead of a silent wait and includes next-step guidance.

### Host Bridge Handoff Recovery

If a run is blocked with:

`BLOCKER: host AI bridge has not completed this handoff`

follow the one-page recovery SOP:

- [Host Bridge Handoff Recovery SOP](core/docs/host-bridge-handoff-sop.md)

## State Layout

All state is stored outside your project directory:

```
~/.agent-crew/state/{PROJECT_STATE_KEY}/tasks/{TASK_ID}/
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
