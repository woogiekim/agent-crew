# Native Crew Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the native Codex crew path from using an expensive full graph and concurrent same-worktree TDD when resolved scope only needs one cohesive implementer.

**Architecture:** Derive execution policy from validated pipeline structure rather than raw task text. Represent TDD ownership with an explicit mode, keep legacy pipeline input readable, and enforce unchanged-wait limits in the provider-neutral lifecycle state machine.

**Tech Stack:** Python 3 standard library, pytest, Markdown runtime contracts

**Spec:** `docs/superpowers/specs/2026-09-29-native-crew-latency-design.md`

## Global Constraints

- Preserve the mandatory Red, Green, refactor, and independent reviewer gates.
- Never run two mutating agents concurrently in one worktree.
- Keep `tdd_parallel: true` readable as legacy input.
- Select native profiles only from resolved pipeline state.
- Make no remote writes.

## Review Focus

- A ticket-only task must not be classified before pipeline scope is resolved.
- A single implementation stage with a later reviewer must choose `single_agent_tdd`.
- Multiple implementers or independent units must stay on `full_crew`.
- Legacy `tdd_parallel: true` must normalize to a safe sequential mode.
- Any progress fingerprint change must reset the unchanged-wait counter.

---

### Task 1: Resolved native execution profile

**Files:**
- Modify: `core/scripts/quality_loop_lib.py`
- Modify: `core/scripts/pipeline-quality-plan-check.py`
- Test: `tests/python/test_pipeline_quality_plan_check.py`

**Interfaces:**
- Consumes: validated `pipeline.json` stages and `mutation_scope`.
- Produces: `native_execution_profile(pipeline) -> dict` and `execution_profile` in validation output.

- [ ] **Step 1: Write failing tests** for read-only, cohesive single-implementer, multiple implementation stages, and independent fan-out units.
- [ ] **Step 2: Run the focused tests** and confirm the profile function/output is missing.
- [ ] **Step 3: Implement the profile resolver** from normalized pipeline structure.
- [ ] **Step 4: Run the focused tests** and confirm all profile cases pass.
- [ ] **Step 5: Record the verified checkpoint** in the execution ledger; local commit remains a separate user action.

### Task 2: Safe TDD mode normalization

**Files:**
- Modify: `core/scripts/quality_loop_lib.py`
- Modify: `core/scripts/pipeline-quality-plan-check.py`
- Modify: `core/rules/state-files/pipeline-json.md`
- Test: `tests/python/test_pipeline_quality_plan_check.py`

**Interfaces:**
- Consumes: stage objects with `tdd_mode` or legacy `tdd_parallel`.
- Produces: `stage_tdd_mode(stage) -> str` and validated implementation-stage mode metadata.

- [ ] **Step 1: Write failing tests** for `inline`, `sequential_pair`, `isolated_parallel`, invalid modes, and legacy normalization.
- [ ] **Step 2: Run the focused tests** and confirm the new mode cases fail for the expected reason.
- [ ] **Step 3: Implement normalization and validation** while keeping old data readable.
- [ ] **Step 4: Update the state-file contract** with exact ownership and compatibility rules.
- [ ] **Step 5: Run focused quality-plan tests** and record the Green checkpoint.

### Task 3: Shared-worktree dispatch contract

**Files:**
- Modify: `core/agents/supervisor-stages.md`
- Modify: `core/agents/analyst.md`
- Modify: `core/agents/skills/pipeline-planning.md`
- Modify: `core/agents/test-writer.md`
- Test: `tests/python/test_pipeline_quality_plan_check.py`

**Interfaces:**
- Consumes: normalized `tdd_mode` selected by the pipeline gate.
- Produces: inline or sequential dispatch instructions where the last writer owns final Green.

- [ ] **Step 1: Add a failing contract test** that rejects same-worktree parallel mutation wording and requires the three modes.
- [ ] **Step 2: Run the contract test** and observe the old co-spawn wording fail.
- [ ] **Step 3: Replace the dispatch contract** with inline, sequential-pair, and isolated-parallel routing.
- [ ] **Step 4: Update planner and test-writer guidance** to emit and follow the safe modes.
- [ ] **Step 5: Run focused contract tests** and record the Green checkpoint.

### Task 4: Deterministic unchanged-wait bound

**Files:**
- Modify: `core/scripts/stage_lifecycle.py`
- Modify: `core/agents/supervisor-retry.md`
- Test: `tests/python/test_stage_lifecycle.py`

**Interfaces:**
- Consumes: a progress fingerprint for each bounded wait observation.
- Produces: `record_wait_observation(state, fingerprint, at)` and `interrupt_and_inspect` after two unchanged waits.

- [ ] **Step 1: Write failing tests** for first observation, second unchanged observation, progress reset, and terminal-state precedence.
- [ ] **Step 2: Run the focused lifecycle tests** and confirm the helper is missing.
- [ ] **Step 3: Add lifecycle wait state and deterministic decisions** with a default limit of two.
- [ ] **Step 4: Document the supervisor call sequence** around wait, observe, decide, and interrupt.
- [ ] **Step 5: Run focused lifecycle tests** and record the Green checkpoint.

### Task 5: Integrated verification and review

**Files:**
- Test: `tests/python/test_current_session_execution_gate.py`
- Test: `tests/python/test_pipeline_quality_plan_check.py`
- Test: `tests/python/test_stage_lifecycle.py`

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: one verified diff and an independent final review.

- [ ] **Step 1: Run the three focused suites** and confirm all pass.
- [ ] **Step 2: Run the broader Python test suite** with bytecode and pytest cache disabled.
- [ ] **Step 3: Inspect the complete diff** for unrelated changes and generic BDD comments.
- [ ] **Step 4: Request one independent whole-branch review** and classify findings by effect.
- [ ] **Step 5: Fix Important findings through Red and Green, then rerun the relevant suite.**
