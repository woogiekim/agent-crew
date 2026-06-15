# Superpowers Plugin Benchmark — Findings

## 1. Executive Summary

This document benchmarks Claude's official "superpowers" plugin (v5.1.0) against the agent-crew architecture to identify improvement opportunities. The superpowers plugin provides 14 discipline-focused skills covering workflow orchestration, design-before-code gates, test-driven development, code review discipline, and developer tooling patterns.

Agent-crew already implements the core patterns behind all 14 superpowers skills, though often in different shape. The key finding is that **zero clean adopts emerge from the AI-agnostic posture filter**: every superpowers skill is either (a) already covered by an existing agent-crew mechanism in a more robust form, or (b) depends on Claude-specific tools (Skill dispatcher, Task subagent API, TodoWrite, EnterPlanMode, EnterWorktree) that cannot translate cleanly to other LLM hosts. This is the expected outcome when the design axiom is host-agnostic.

The benchmark produces **9 adapt recommendations** and **5 exclude verdicts**, split by ship-threshold as follows:
- **Ship-threshold pass (Y): 5 candidates** — operator gains visible delta (faster retries, focused rejection reasons, structured menus, complete PRD specs, or recovery attempts)
- **Ship-threshold fail (N, defer-by-default): 4 candidates** — internal hygiene or low-frequency authoring patterns with no immediate user-visible impact

The top 3 adopt candidates by impact are:

1. **Self-verification discipline for non-reviewer agents** — Implementers run test suites before emitting STATUS: completed, reducing reviewer-loop-back retry rounds (ship-threshold: Y, impact: medium-high, effort: S)
2. **Two-stage review split (spec compliance → code quality)** — Reviewer runs PRD coverage gate first, then code-quality checks, so rejection reasons distinguish scope gaps from polish issues (ship-threshold: Y, impact: medium, effort: S)
3. **3-failures → question architecture recovery** — When an implementer hits 3 consecutive rejections for the same surface, the system escalates to decomposition or restructure prompts before BLOCKED (ship-threshold: Y, impact: medium, effort: S)

The next explicit-pick session should prioritize these three as quick wins; the remaining six (Findings 4–9) are lower-impact or defer-able.

## 2. Skill-by-Skill Mapping Table

| superpowers skill | agent-crew counterpart | exists / partial / missing | verdict |
|---|---|---|---|
| using-superpowers | `core/rules/agent-skill-loading.md:12-32` | partial | exclude |
| brainstorming | `core/agents/analyst.md` + `core/agents/designer.md:194-241` | partial | adapt |
| writing-plans | `core/agents/analyst.md` Step 6-7, `core/agents/planner.md:138-200` | partial | adapt |
| executing-plans | `core/agents/supervisor-stages.md:16-200` | exists | exclude |
| subagent-driven-development | `core/agents/supervisor.md:200-208`, `core/agents/reviewer.md` | partial | adapt |
| dispatching-parallel-agents | `core/agents/supervisor-stages.md`, `core/commands/run.md:1281-1299` | exists | exclude |
| test-driven-development | `core/agents/test-writer.md:18-35`, `core/agents/skills/tdd.md:1-32`, `core/rules/quality-loop.md:49-77` | exists | exclude |
| systematic-debugging | none (no dedicated debugging agent or rule) | missing | adapt |
| verification-before-completion | `core/rules/quality-loop.md:36-47`, `core/rules/quality-loop.md:301-345` | partial | adapt |
| requesting-code-review | `core/agents/supervisor-stages.md`, `core/agents/reviewer.md`, `core/agents/skills/code-review.md:1-72` | exists | exclude |
| receiving-code-review | `core/agents/supervisor-retry.md:203-305` | partial | adapt |
| using-git-worktrees | `core/commands/run.md:1281-1299`, `core/agents/supervisor-stages.md` | exists | exclude |
| finishing-a-development-branch | `core/agents/supervisor-retry.md:462-512`, `core/commands/run.md` Step 11 | partial | adapt |
| writing-skills | `core/agents/skills/SKILL-TEMPLATE.md`, `core/rules/agent-skill-loading.md` | partial | adapt |

## 3. Detailed Findings per Improvement Opportunity

### 3.1. Two-stage review split (spec-compliance THEN code-quality) — verdict: ADAPT

- **Source (superpowers):** `subagent-driven-development` skill — dispatches a spec-compliance reviewer subagent (confirms code matches PRD), then a code-quality reviewer subagent (polishes, approves). Two distinct review phases with strict ordering.
- **agent-crew current state:** `core/agents/reviewer.md:11-13` combines spec coverage AND code-quality findings in a single pass. The code-review skill at `core/agents/skills/code-review.md:13-45` interleaves PRD coverage analysis with git diff analysis in one review phase.
- **Gap:** When the reviewer rejects, the implementer receives a single REJECTED verdict that may cite both "missing acceptance criterion #3" and "magic number in foo.kt". The two-stage split forces scope gaps to resolve first, so implementers fix PRD compliance before polishing.
- **Verdict rationale:**
  - **AI-agnostic posture:** Both stages are subagent spawns the supervisor already issues; no Claude-specific tooling.
  - **Ship-threshold:** Y — operator sees more focused rejection reasons; spec_incomplete vs code_quality distinctions reduce retry noise.
  - **Prior decisions:** Does not re-litigate Big Five AAR (#129), SMM, or Mutual Trust.
- **Suggested follow-up shape:** `core/agents/reviewer.md` adds a Phase 1.7 PRD Coverage Gate that runs the coverage matrix first and returns `STATUS: REJECTED REASON: spec_incomplete` (new reason); only after spec is complete does Phase 2 run.
- **Impact:** Medium
- **Effort:** S

### 3.2. Self-verification discipline for non-reviewer agents — verdict: ADAPT

- **Source (superpowers):** `verification-before-completion` skill — "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE … If you haven't run the verification command in THIS message, you cannot claim it passes."
- **agent-crew current state:** `core/rules/quality-loop.md:36-47` documents acceptance criteria; `core/rules/quality-loop.md:301-345` Issue #3 adds reviewer test execution as a gate. `core/agents/backend.md:55-90` and `core/agents/test-writer.md` do not explicitly require implementers to run test suites before emitting `STATUS: completed`.
- **Gap:** Agent-crew leans on the reviewer to catch "implementer claimed completion without running tests". That's Issue #3, but it shifts every verification to the reviewer stage. Implementers can still emit `STATUS: completed` based on static reasoning, triggering a quality-loop retry.
- **Verdict rationale:**
  - **AI-agnostic posture:** Running test commands is provider-neutral.
  - **Ship-threshold:** Y — fewer reviewer-side rejections for missing evidence; faster iteration.
  - **Prior decisions:** Complementary to Big Five AAR (settled #129).
- **Suggested follow-up shape:** New `core/rules/self-verification.md` rule cited by every implementation agent's quality-loop block, requiring a `VERIFIED: tests=passed (cmd=<cmd>)` evidence line in the completion report.
- **Impact:** Medium-high
- **Effort:** S

### 3.3. Systematic-debugging 4-phase model with "3 failures → question architecture" — verdict: ADAPT

- **Source (superpowers):** `systematic-debugging` skill — Phase 1 root cause investigation / Phase 2 pattern analysis / Phase 3 hypothesis / Phase 4 implement. "If 3+ fixes fail: Question Architecture."
- **agent-crew current state:** `core/rules/evidence-grounded-reasoning.md:33-46` covers Evidence → Inference → Conclusion. Quality loop retry budget at `core/rules/quality-loop.md:18-20` is "3 retries then BLOCKED" — purely mechanical.
- **Gap:** When an implementer hits 3 consecutive reviewer rejections, the system halts with `quality_loop_exhausted`. Superpowers' "question architecture" gate is a recovery prompt — the agent should decompose or restructure rather than fail.
- **Verdict rationale:**
  - **AI-agnostic posture:** No Claude-specific tooling; decomposition and refactoring are universal.
  - **Ship-threshold:** Y — one more recovery attempt before BLOCKED; reduces terminal blockers.
  - **Prior decisions:** Complementary to Big Five AAR; BLOCKED Recovery at `core/rules/quality-loop.md:262-275` is the insertion point.
- **Suggested follow-up shape:** Extend `core/rules/quality-loop.md` § BLOCKED Recovery with: "if same failure surface for ≥3 retries: issue directive to decompose or restructure".
- **Impact:** Medium
- **Effort:** S

### 3.4. "No Placeholders" enforcement for PRD / pipeline.json content — verdict: ADAPT

- **Source (superpowers):** `writing-plans` skill — forbids "TBD, TODO, implement later, fill in details, add appropriate error handling". Plan self-review scans for these patterns.
- **agent-crew current state:** `core/agents/analyst.md` Step 7 writes the PRD; no automated placeholder scan. Reviewer can flag missing criteria but does not block the analyst on placeholder-laden PRDs.
- **Gap:** Analyst writes a PRD with "TODO: define acceptance criteria for edge cases"; pipeline proceeds. Test-writer then derives tests from an under-specified contract.
- **Verdict rationale:**
  - **AI-agnostic posture:** Pattern scan via regex is provider-neutral.
  - **Ship-threshold:** Y — Phase 2 receives complete specs; analyst rewrites incomplete PRDs before proceeding.
  - **Prior decisions:** Does not re-litigate settled decisions.
- **Suggested follow-up shape:** Extend `core/scripts/pipeline-quality-plan-check.py` with placeholder-scan on `prd.md` content; analyst must rewrite before emitting `pipeline.json`.
- **Impact:** Low-medium
- **Effort:** S

### 3.5. Structured close-out menu (merge / PR / keep / discard) — verdict: ADAPT

- **Source (superpowers):** `finishing-a-development-branch` skill — 4 options (merge locally / push+PR / keep as-is / discard) or 3 for detached HEAD.
- **agent-crew current state:** `core/commands/run.md` Step 11 single push-approval gate. The orchestrator handles push; no in-band "merge locally vs PR vs discard" menu exists.
- **Gap:** Operator sees "approve push?" but cannot say "merge locally first" without manual git work.
- **Verdict rationale:**
  - **AI-agnostic posture:** Uses `core/rules/capabilities/interactive-question.md` structured-choice intent (agent-crew already owns this).
  - **Ship-threshold:** Y, low-impact — operator gains discard option that currently requires manual cleanup.
  - **Prior decisions:** Does not re-litigate settled decisions.
- **Suggested follow-up shape:** Extend `core/commands/run.md` Step 11 from Y/N push-approve into a structured choice.
- **Impact:** Low-medium
- **Effort:** M

### 3.6. Anti-rationalization tables in implementation agent prompts — verdict: ADAPT (defer-by-default)

- **Source (superpowers):** Skills `test-driven-development`, `verification-before-completion`, `receiving-code-review` each contain a "Common Rationalizations" table.
- **agent-crew current state:** `core/agents/test-writer.md` enforces TDD via mechanism. `core/rules/quality-loop.md` has clean rules but no explicit rationalization table.
- **Gap:** When non-test-writer agents face retry pressure, there's no in-prompt anti-rationalization defense.
- **Verdict rationale:**
  - **AI-agnostic posture:** Agent prompts already contain rules; adding rationalization tables is documentation.
  - **Ship-threshold:** N — operator does not see direct user-visible delta; benefit is risk reduction during retries.
  - **Prior decisions:** Does not re-litigate settled decisions.
- **Suggested follow-up shape:** Add small "Rationalizations" appendix to each implementation agent listing 4–6 common pressure rationalizations and counter-text.
- **Impact:** Low
- **Effort:** S

### 3.7. "Description must NOT summarize workflow" rule for skill discovery — verdict: ADAPT (defer-by-default)

- **Source (superpowers):** `writing-skills` skill — "Description = When to Use, NOT What the Skill Does."
- **agent-crew current state:** `core/rules/agent-skill-loading.md:12-32` mandates registry but does NOT prescribe description-field discipline.
- **Gap:** Agent dispatcher behavior can short-circuit on skill descriptions.
- **Verdict rationale:**
  - **AI-agnostic posture:** AI-agnostic discipline; no vendor tooling.
  - **Ship-threshold:** N — internal hygiene affecting skill discovery quality.
  - **Prior decisions:** Does not re-litigate settled decisions.
- **Suggested follow-up shape:** Amend `core/rules/agent-skill-loading.md` with "Description Field Discipline" section.
- **Impact:** Low
- **Effort:** S

### 3.8. Multi-component instrumentation pattern for cross-layer debugging — verdict: ADAPT (defer-by-default)

- **Source (superpowers):** `systematic-debugging` skill — "For EACH component boundary: Log what data enters/exits".
- **agent-crew current state:** `core/rules/quality-loop.md:336-345` § Cross-process path agreement check — reviewer grep-compares path literals.
- **Gap:** Agent-crew has the static check; superpowers adds a runtime instrumentation step. They are complementary.
- **Verdict rationale:**
  - **AI-agnostic posture:** Bash + env + log are provider-neutral.
  - **Ship-threshold:** N — Issue-#3 static check already covers common case.
  - **Prior decisions:** Does not re-litigate settled decisions.
- **Suggested follow-up shape:** Optional debugging-mode skill at `core/agents/skills/cross-layer-debugging.md`.
- **Impact:** Low
- **Effort:** S

### 3.9. TDD-applied-to-skill-authoring methodology — verdict: ADAPT (defer-by-default)

- **Source (superpowers):** `writing-skills` skill — RED (pressure-scenario without skill) → GREEN (write skill) → REFACTOR.
- **agent-crew current state:** `core/agents/skills/SKILL-TEMPLATE.md` exists; skills are written declaratively without documented pressure-test methodology.
- **Gap:** New skills are added without baseline-failure trace.
- **Verdict rationale:**
  - **AI-agnostic posture:** Uses subagent invocations agent-crew already supports.
  - **Ship-threshold:** N — internal authoring-process improvement; low-frequency.
  - **Prior decisions:** Does not re-litigate settled decisions.
- **Suggested follow-up shape:** Extend `core/agents/skills/SKILL-TEMPLATE.md` with "RED phase" preamble template.
- **Impact:** Low
- **Effort:** S

## 4. Prioritized Adoption Backlog

| # | Candidate | Impact | Effort (S/M/L) | Ship-threshold pass? | Verdict |
|---|---|---|---|---|---|
| 1 | Finding 2 — Self-verification discipline for non-reviewer agents | medium-high | S | Y — reviewer-loop-back retry rounds drop | ADAPT |
| 2 | Finding 1 — Two-stage review split (spec then quality) | medium | S | Y — focused rejection reasons; spec_incomplete vs code_quality | ADAPT |
| 3 | Finding 3 — "3 failures → question architecture" recovery | medium | S | Y — fewer terminal blockers; recovery attempt | ADAPT |
| 4 | Finding 5 — Structured close-out menu | low-medium | M | Y — operator gains discard / local-merge paths | ADAPT |
| 5 | Finding 4 — Placeholder scan on PRD content | low-medium | S | Y — Phase 2 receives complete specs | ADAPT |
| 6 | Finding 6 — Anti-rationalization tables | low | S | N — internal hygiene, no user-visible delta | ADAPT (defer) |
| 7 | Finding 7 — Description-field discipline | low | S | N — internal skill-discovery hygiene | ADAPT (defer) |
| 8 | Finding 8 — Cross-layer debugging skill | low | S | N — Issue-#3 static check covers case | ADAPT (defer) |
| 9 | Finding 9 — TDD-skill-authoring template | low | S | N — authoring-process improvement | ADAPT (defer) |

## 5. Out-of-Scope / Already-Decided

This benchmark checked but explicitly defers re-evaluation of three settled decisions:

- **Big Five AAR (After-Action Review) loop** — ADOPTED (#129). This benchmark does NOT propose changes to AAR mechanics. Finding 3 (mid-run recovery via decomposition) is complementary to post-hoc AAR — a distinct mechanism. Confirmed: no re-litigation.
- **Shared Mental Model (SMM)** — DEFERRED. No recommendation re-introduces a shared global state model. All recommendations preserve the hub-and-spoke model. Confirmed: no re-litigation.
- **Mutual Trust** — EXCLUDED. No recommendation proposes inter-agent trust signaling beyond existing review verdict + reviewer loop-back semantics. Finding 1 (two-stage review split) is intra-agent (reviewer internal phases), not inter-agent trust. Confirmed: no re-litigation.

## 6. Evidence Notes

| Evidence | Inference | Conclusion |
|---|---|---|
| Superpowers' five mechanisms depend on Claude Code specific tools (Skill dispatcher, Task API, TodoWrite, EnterPlanMode, EnterWorktree). Agent-crew is multi-host (Codex, generic + Claude bridge). | AI-agnostic posture forbids Claude-only mechanisms as clean adopts because they cannot degrade on alternate hosts. | All 5 are classified EXCLUDE (already covered in more robust form or irrelevant to multi-host design). Zero clean ADOPT verdicts. |
| Ship-threshold filter requires user-visible delta to clear; internal hygiene is defer-by-default. Findings 6–9 are documentation, optional skills, authoring-process hygiene. | Internal-only work is assumed defer-by-default absent explicit operator request. | Findings 6–9 carry ship-threshold=N and are marked defer-by-default. |
| Findings 1–5 each reduce retry counts, clarify signals, enable recovery, or prevent under-specified PRDs. Validated against PRD acceptance criteria and handoff constraints. | Visible operator benefit is the ship-threshold pass criterion. | Findings 1–5 carry ship-threshold=Y and ranked by impact in backlog. Next explicit-pick session should implement these in priority order. |

