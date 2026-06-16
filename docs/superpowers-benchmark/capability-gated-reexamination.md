# Superpowers Plugin Benchmark — Capability-Gated Re-Examination (Third Pass)

**Date:** 2026-06-15  
**Scope:** Re-frames the prior two passes' EXCLUDE verdicts on six superpowers mechanisms under agent-crew's existing capability-gating precedent.  
**Lineage:** Builds on `docs/superpowers-benchmark/findings.md` (Phase 1–2) with a new analytical lens: AI-agnostic posture permits Claude-only host surfaces **IF** they degrade gracefully to file-based fallbacks.

## Executive Summary

The first two benchmark passes applied an AI-agnostic filter that read "Claude-only mechanism → cannot be a clean adopt." This was overly conservative. Agent-crew's own capability-gating precedent—visible in `core/rules/capabilities/task-tools.md`, `agent-background.md`, and `interactive-question.md`—demonstrates that Claude-only host surfaces **are** adoptable as augmentations, provided they satisfy two invariants: a documented Absence Contract in `capabilities.json`, and a file-based fallback that preserves AI-agnostic posture on every other host.

The reframe sharpens the filter from "no Claude-only surfaces" to "no uncontrolled host coupling." Under this lens, six superpowers mechanisms resolve as follows: **0 ADOPT-AS-CAPABILITY**, **1 ADAPT** (file-only, defer-by-default), **4 keep-EXCLUDE-because-already-covered**, and **1 keep-EXCLUDE-honest** (the existing portable bash path is superior to a host-side variant). No new framework code is written—the goal is findings only, grounding the prior verdicts in sharper reasoning and confirming that agent-crew's foundational axiom is anti-uncontrolled-coupling, not blanket anti-Claude.

## Per-Mechanism Reframe Table

| Mechanism | Prior Verdict (findings.md) | Proposed Capability Flag | Abstract Capability / Fallback | Revised Verdict | Ship-Threshold | Effort |
|---|---|---|---|---|---|---|
| **Skill dispatcher** | EXCLUDE (row 1) | n/a | Already covered by `core/rules/agent-skill-loading.md:12-32` + skill-load evidence files; host dispatcher adds unaudited path | keep-EXCLUDE-because-already-covered | N | — |
| **Task subagent API** | EXCLUDE (row 6, implicit via dispatching-parallel-agents framing) | n/a | This IS the precedent: `core/rules/capabilities/task-tools.md` + `adapters/claude/setup.sh:247-256` | keep-EXCLUDE-because-already-covered | pass (shipped) | — |
| **TodoWrite** | EXCLUDE (Evidence Notes row) | `todo_surface` (proposed but rejected) | File fallback: `${TASK_DIR}/context/todos.md` (markdown checklist); host mirror fails ship-threshold vs. existing `task_tools` UI | ADAPT (file-only) | N | S |
| **EnterPlanMode / Plan mode** | EXCLUDE (Evidence Notes row) | n/a | Already covered by `core/rules/capabilities/interactive-question.md:1-95` with `_mode` field at `core/rules/host-capabilities.md:67` | keep-EXCLUDE-because-already-covered | N | — |
| **EnterWorktree** | EXCLUDE (row 12, "exists") | n/a | Existing bash path at `core/commands/run.md:1281-1346` is portable with guards; host surface would regress AI-agnostic property | keep-EXCLUDE-honest | N | — |
| **dispatching-parallel-agents** | EXCLUDE (row 6, "exists") | n/a | Already covered by `agent_background` (`core/rules/capabilities/agent-background.md:30-58`) + `parallelizable_units` (`core/agents/supervisor-stages.md:699-742`) | keep-EXCLUDE-because-already-covered | pass (shipped) | — |

## Detailed Findings Per Mechanism

### Skill Dispatcher

The superpowers `using-superpowers` skill instructs the model to invoke Skill tools by name, triggered on user-phrasing matches. Agent-crew already implements skill loading in a more auditable form.

Agent-crew's `core/rules/agent-skill-loading.md:12-32` defines the `## Skills (Loaded On Demand)` section as the authoritative skill declaration. Each implementation agent documents the Skills section in its own prompt; the analyst stage writes `${TASK_DIR}/context/{agent}-skill-load.md` as evidence (see `core/agents/analyst.md:100-105` and `core/agents/analyst.md:170-175`); and the supervisor validates this evidence at `core/agents/supervisor-bootstrap.md:810`. The entire path is file-based and auditable from within the task directory.

A host-side Skill dispatcher would create a parallel discovery mechanism alongside this, visible only in the host UI. The two paths would eventually drift; one would become a second source of truth. Per the AI-agnostic invariant at `core/rules/host-capabilities.md:13-16`, audit trails must not depend on host UI visibility. Adopting a host dispatcher would therefore be a regression in auditability, even on Claude.

**Revised verdict:** keep-EXCLUDE-because-already-covered. The IDEA (context-aware skill loading) is already implemented in a stronger form. Ship-threshold: N.

### Task Subagent API

The superpowers `dispatching-parallel-agents` and `subagent-driven-development` skills fan out work into Claude Code's native Task subagents with structured lifecycle (create / get / update / list / output streaming).

This is the foundational precedent for agent-crew's capability gating. `core/rules/capabilities/task-tools.md:1-46` documents the abstract contract: `createTask`, `listTasks`, `getTask`, `updateTask`, `getTaskOutput`. The adapter writes `task_tools: true` and `agent_background: true` at `adapters/claude/setup.sh:247-256`. Every consumer is gated by `HAS_TASK_TOOLS`: `core/agents/supervisor-bootstrap.md:103-110` and `core/agents/supervisor-stages.md:1636-1696`. The latter shows the paired architecture: on Claude, long-poll via TaskGet; on Codex/generic, 5-second poll on `approval.md`. Both paths write the same artifact.

The superpowers Task API is not a new mechanism—it IS the mechanism agent-crew built the precedent on.

**Revised verdict:** keep-EXCLUDE-because-already-covered. The mechanism is already shipped as part of the `task_tools` flag. Ship-threshold: pass (historically shipped). No new work.

### TodoWrite

Superpowers' TodoWrite surface writes a host-managed todo list visible in the Claude UI. Agent-crew can adopt the IDEA (granular, persistent checklist) while declining the host-side mirror until user-visible delta justifies it.

The pattern precedent is `monitor_tool` at `core/rules/capabilities/monitor-tool.md:1-47`: Claude exposes a streaming output surface (`TaskOutput`) for live visibility; agent-crew gates it via `HAS_MONITOR_TOOL` and falls back to tailing `progress.buffer.jsonl`. The file is canonical; the host surface mirrors it.

For TodoWrite, the proposed file fallback is `${TASK_DIR}/context/todos.md`—a markdown checklist with items keyed by `stage:agent:phase`, updated at the same supervisor checkpoints that already write `progress.log`. This file requires zero host capabilities and works on every adapter. The supervisor can additionally call TodoWrite on Claude to mirror the same checklist into the host UI.

However, applying the ship-threshold test from memory `feedback_ship-threshold.md`—"user-visible delta required"—the host mirror fails. Agent-crew's `task_tools` flag already provides live, per-stage progress visibility via the host's native task DAG. A parallel todo-list surface would largely duplicate that, with marginal improvement. Per the memory guidance, hygiene-only augmentations are defer-by-default.

**Revised verdict:** ADAPT (file-only). The markdown `todos.md` artifact is adoptable immediately without any new flag; the host mirror should be deferred pending independent demonstration of user-visible delta beyond what `task_tools` already provides. Ship-threshold: N (overlaps with existing `task_tools` win; hygiene-only on top). Effort: S (file artifact) or M (if host mirror is added later).

### EnterPlanMode / Plan mode

Superpowers' EnterPlanMode transitions the model into "Plan mode"—a structured interaction surface where the model produces a plan, the user approves it via a native prompt, and only then does execution proceed.

Agent-crew has a direct precedent: `core/rules/capabilities/interactive-question.md:1-95` defines the abstract contract `askQuestion(prompt, options[])`, which yields a finite labeled choice. The supervisor approval gate at `core/agents/supervisor-stages.md:1703-1706` uses this for devops/destructive-action approval. The `interactive_question_mode` field at `core/rules/host-capabilities.md:67` already contemplates `codex_plan_mode_conditional` as one rendering of this same capability.

Claude's native plan-mode is a **binding**—a host-specific way to invoke the abstract `askQuestion` capability. The file-based fallback is `${TASK_DIR}/context/action-plan.md` + markdown options at `core/rules/capabilities/interactive-question.md:60-77`: "Pick one (reply with the option number): 1. {label} … 0. cancel".

The IDEA (structured plan + structured approval) is already covered. Mapping it to Claude's plan-mode is an adapter-binding refinement (in `invocation.md`), not a new capability gate.

**Revised verdict:** keep-EXCLUDE-because-already-covered. Optional follow-up: refine the Claude `invocation.md` mapping to bind `askQuestion` calls to plan-mode where preferable (e.g., approval gates). That is adapter tuning, not a new flag. Ship-threshold: N.

### EnterWorktree

Superpowers' `using-git-worktrees` skill delegates worktree creation to host tooling. Agent-crew creates worktrees portably in bash.

The canonical implementation at `core/commands/run.md:1281-1346` runs `git worktree add` in bash with three documented guards: linked-worktree detection, submodule probe, and `.crew-worktrees/` ignore verification. The comment at `core/commands/run.md:1290-1291` explicitly states: "These guards keep the harness AI-agnostic (bash + git only) and prevent nested-worktree, submodule, and untracked-isolation-directory regressions."

A host-side `EnterWorktree` tool would shift guard semantics out of the core bash script into the host. The host implementation would need to replicate the same guards; if it diverges, breakage occurs. The operator sees no performance benefit (I/O is overlapped at `core/commands/run.md:1285-1287` during requirements collection). A second, parallel worktree path adds maintenance burden and drift risk.

This is keep-EXCLUDE for a sharper reason than "Claude-only": **the existing portable bash path is technically superior.** Adding a gated alternate would be a regression in code quality, not a feature addition.

**Revised verdict:** keep-EXCLUDE-honest (the host surface is worse than the existing AI-agnostic implementation; the exclusion stands for a strengthened reason). Ship-threshold: N.

### dispatching-parallel-agents

Superpowers' `dispatching-parallel-agents` skill fans out independent work units into concurrent Claude Task subagent invocations within a single host message.

Agent-crew implements parallel dispatch in two complementary precedents. First, supervisor-level fan-out for `crew:run N>1` is gated by `agent_background` at `core/rules/capabilities/agent-background.md:30-58`: when true, supervisors spawn as background agents; when false, the orchestrator runs them inline. Second, sub-task fan-out within a single supervisor is implemented as `parallelizable_units` at `core/agents/supervisor-stages.md:699-742`, which dispatches N parallel agents in one host message with a resolver pre-flight overlap check at `core/agents/supervisor-stages.md:728-742`.

Both paths use the same supervisor-layer abstraction. The host-side acceleration (concurrent spawn) is an augmentation gated through `agent_background`. The fallback is identical structure on every adapter: when `agent_background=false`, the orchestrator runs the same units inline.

The superpowers mechanism IS a description of the behavior the `agent_background` flag already ships.

**Revised verdict:** keep-EXCLUDE-because-already-covered. This is the second precedent-of-record alongside `task_tools`. Ship-threshold: pass (shipped). No new work.

## Cross-Mechanism Observations

**Pattern 1: Most exclusions are "already covered," not "impossible."** Four of six mechanisms (Task subagent API, EnterPlanMode, dispatching-parallel-agents, Skill dispatcher) pattern directly onto existing agent-crew capability flags or AI-agnostic conventions. The first two passes' EXCLUDE verdicts were correct in outcome but imprecise in language. They cited "Claude-only" when the precise reason was "the IDEA is already implemented in a more auditable / performant / portable form." The third-pass reframe clarifies this distinction and removes the misleading suggestion that AI-agnostic posture is anti-Claude. It is **anti-uncontrolled-host-coupling**—which happens to exclude many Claude-only surfaces *because they lack fallbacks*, not because Claude-ness is intrinsically forbidden.

**Pattern 2: New-flag candidates are rare.** Only TodoWrite presented a plausible new-flag candidate. Even then, the ship-threshold test rejected it: the user-visible delta on Claude (a secondary checklist surface) largely overlaps with what `task_tools` already delivers. EnterWorktree is the only mechanism where a host surface would be *worse* than the existing path, making exclusion a code-quality call rather than an AI-agnostic call. This finding echoes the benchmark's headline conclusion: "zero clean adopts emerge from the AI-agnostic posture filter." The reframe sharpens the reasoning but does not shift the numerical outcome.

**Pattern 3: When new flags are justified, the file fallback precedes the flag.** The TodoWrite analysis surfaces the right adoption sequence for any future host-surface augmentation: (a) author and stabilize the file artifact first (`${TASK_DIR}/context/todos.md`), make it the canonical source of truth, exercise it across every adapter; (b) only when the user-visible delta on the host is independently demonstrated should a new `_surface` flag be added, mirroring the same content into host UI. This mirrors the actual history of `task_tools` (Phase 0 supervisor wrote `pipeline.json` long before TaskCreate existed). It would be a mistake to introduce a new flag whose audit trail lives only in the host UI.

## Prioritized Adopt-as-Capability Backlog

**(empty — no proposed flag clears the ship-threshold in this pass)**

The TodoWrite file artifact (`todos.md`) is adoptable immediately, but as ADAPT (no new flag), and it is defer-by-default per memory `feedback_ship-threshold.md`. No mechanism qualifies for ADOPT-AS-CAPABILITY.

The verdict distribution is:
- **0 ADOPT-AS-CAPABILITY** — no new flag passes ship-threshold
- **1 ADAPT** — TodoWrite file-only (defer-by-default)
- **4 keep-EXCLUDE-because-already-covered** — Skill dispatcher, Task subagent API, EnterPlanMode, dispatching-parallel-agents
- **1 keep-EXCLUDE-honest** — EnterWorktree (host surface would regress the portable bash path)

## Honesty Note

The third pass arrived at substantially the same EXCLUDE outcome as the prior two passes. This is not a failure of analysis, but a validation of it. The novel contribution is **why** the verdicts hold.

The first two passes filtered via "Claude-only → not adoptable." This filter was overly broad because it conflated *surface* with *behavior*. The corrected filter is "Claude-only surface WITHOUT (a documented fallback AND user-visible delta) → not adoptable." Under the corrected filter:

- Four mechanisms prove to be already-covered precedents, strengthening the exclusion from a linguistic position to a technical one.
- One mechanism (TodoWrite) reveals a file-based fallback, but the user-visible delta does not clear ship-threshold, yielding ADAPT-but-defer instead of ADOPT.
- One mechanism (EnterWorktree) reveals that a host surface would *degrade* the existing implementation, making exclusion a code-quality call rather than an AI-agnostic posture call.

Agent-crew's foundational axiom—"be multi-host, gating Claude-only surfaces through capabilities.json with file-based fallbacks"—survives this reexamination intact and stronger.

## References

**Existing capability flags (precedent-of-record):**
- `core/rules/capabilities/task-tools.md:1-46` — abstract contract
- `core/rules/capabilities/task-tools.md:78-87` — Absence Contract
- `core/rules/capabilities/agent-background.md:30-58` — background-agent gating
- `core/rules/capabilities/interactive-question.md:1-95` — structured-choice contract
- `core/rules/capabilities/interactive-question.md:60-77` — Absence Behavior (markdown fallback)
- `core/rules/capabilities/monitor-tool.md:1-47` — streaming output + file tail fallback
- `core/rules/host-capabilities.md:13-16` — Invariant 1 (gating + fallback)
- `core/rules/host-capabilities.md:67` — plan-mode rendering

**Supervisor consumption sites:**
- `core/agents/supervisor-bootstrap.md:70-110` — HAS_TASK_TOOLS gating
- `core/agents/supervisor-bootstrap.md:810` — skill-load evidence validation
- `core/agents/supervisor-stages.md:699-742` — parallelizable_units dispatch
- `core/agents/supervisor-stages.md:1636-1696` — approval-gate dual path (TaskGet + approval.md poll)
- `core/agents/supervisor-stages.md:1703-1706` — interactive-question call site

**AI-agnostic skill-loading precedent:**
- `core/rules/agent-skill-loading.md:12-32` — Skills section spec
- `core/agents/analyst.md:100-105`, `core/agents/analyst.md:170-175` — skill-load evidence generation

**Portable worktree implementation:**
- `core/commands/run.md:1281-1346` — bash-only worktree creation with guards
- `core/commands/run.md:1290-1291` — guard justification

**Adapter setup:**
- `adapters/claude/setup.sh:247-256` — capability-flag emission

**Prior benchmark:**
- `docs/superpowers-benchmark/findings.md:1-189` — Phase 1–2 verdicts and evidence (not re-litigated)

**Memory / standing decisions:**
- memory `feedback_ship-threshold.md` — user-visible-delta requirement; hygiene-only defer-by-default
- memory `project_ai-agnostic-posture.md` — AI-agnostic posture is load-bearing
- memory `project_bigfive-adoption.md` — AAR adopted, SMM deferred, Mutual Trust excluded
