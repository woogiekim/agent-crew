# Skill: pipeline-planning

## Purpose
Enables the planner agent to translate a structured requirements block into a concrete agent pipeline, produce a PRD, and write handoff artifacts that downstream agents can consume immediately without further clarification.

## When to Apply
- After requirements have been collected (either passed in or gathered via the requirements agent)
- When a request spans multiple domains (backend + frontend, feature + deploy, etc.)
- When the correct agent sequence or parallelization strategy is unclear
- When evaluating whether a custom agent is needed for a specialized role

---

## PRD Authoring from Requirements

Translate scope/target/constraints answers into a structured Product Requirements Document. Keep goals declarative and implementation-agnostic. For tooling, documentation, prompt, or agent-skill work, frame the PRD around workflow reliability and safety rather than product screens or API behavior.

```markdown
# PRD: {feature name}

## Goals
- {what the feature achieves}

## Core Features
- {feature 1} [Must have]
- {feature 2} [Should have]

## Acceptance Criteria
- AC-001: Given {context} When {action} Then {outcome}

## Non-Functional Requirements
- Performance: {response time / throughput target}
- Security: {auth, data handling}
- Maintainability: KISS, YAGNI, and DRY from `core/rules/code-quality.md`
  must guide implementation and review.
- Availability: {SLA}

## Scope
In: {explicitly included}
Out: {explicitly excluded}

## Will Do
- {smallest concrete implementation tasks}

## Will NOT Do
- No new dependency unless explicitly justified
- No schema/API/infrastructure changes unless required by the request
- No speculative abstraction, cache, queue, or domain expansion

## Diff Budget
- Category: {XS|S|M|L|XL}
- Rationale: {why this is the smallest complete category that satisfies every assigned AC}
```

---

## Minimal-Change Planning Gate

Before writing `pipeline.json`, run the Need Analyzer and Capability Search
from `core/rules/lean-workflow-methodology.md`.

Need Analyzer questions:
- Can this be solved without writing code?
- Can existing project code solve this?
- Can framework functionality solve this?
- Can the standard library solve this?
- Can configuration solve this?
- Can infrastructure solve this?
- Can an existing API solve this?
- Can the feature be removed instead?

Capability Search order:
1. Existing project code
2. Existing utilities
3. Language features
4. Standard library
5. Framework features
6. Third-party libraries already installed
7. Platform capabilities
8. Infrastructure configuration

If any Need Analyzer answer is `yes`, do not emit an implementation stage.
Recommend that non-code/reuse/configuration/deletion route first.

For mutating implementation work, write this machine-readable summary into
`pipeline.json`:

```json
{
  "decision_context": {
    "need_analysis": {
      "can_solve_without_code": "no",
      "existing_project_code": "no",
      "framework_functionality": "no",
      "standard_library": "no",
      "configuration": "no",
      "infrastructure": "no",
      "existing_api": "no",
      "delete_instead": "no"
    },
    "capability_search": [
      "existing_project_code",
      "existing_utilities",
      "language_features",
      "standard_library",
      "framework_features",
      "installed_libraries",
      "platform_capabilities",
      "infrastructure_configuration"
    ],
    "diff_budget": {
      "category": "XS",
      "rationale": "Smallest complete change that satisfies every assigned AC."
    },
    "will_do": ["..."],
    "will_not_do": ["No new dependency.", "No schema change."],
    "selected_solution": "...",
    "new_code_allowed_reason": "..."
  }
}
```

For `L` or `XL`, add `smaller_alternatives_rejected` with concrete reasons.

## Stage Dependency Analysis — Critical Path

Before assigning agents to stages, map data dependencies:

1. List every artifact each agent **produces** and **consumes**.
2. Draw a dependency graph (can be mental or written).
3. Non-code agents with no dependency on each other's outputs → same stage
   (parallel).
4. Agent B that consumes Agent A's output → later stage (sequential).

```
designer produces: design-spec.md
backend  produces: OpenAPI contract, DB schema
frontend consumes: design-spec.md + OpenAPI contract

→ designer runs before frontend implementation (Stage 1)
→ backend and frontend run as separate TDD-capable implementation stages
→ reviewer follows implementation
```

**Critical path rule:** the pipeline duration is bounded by the longest sequential chain, not the sum of all work. Maximize parallelism on the critical path.

---

## Pipeline Stage Composition

Build `stages` as a 2D array where inner arrays run in parallel and outer arrays
run sequentially. Every code implementation stage must use the object form
`{ "agents": ["backend"], "tdd_parallel": true, "acceptance_criteria": ["AC-001"] }`
(or frontend/custom equivalent) and must be followed by a deterministic quality
gate: either a solo `["reviewer"]` stage, or
`{"agents":["qa-owner"],"qa_mode":"verify","qa_loop_target":"previous_implementation"}`
followed by a solo `["reviewer"]`. Do not emit bare code stages for new
implementation work, and do not batch multiple code implementation stages
before one quality gate.

For mutating implementation work, assign every PRD `AC-*` item to at least one
implementation or QA-verification stage through that stage's
`acceptance_criteria` field. "Smallest complete" means the smallest stage set
that closes all Must and mapped acceptance criteria, not a partial
implementation that leaves PRD behavior unowned.

| Scope | stages |
|---|---|
| Backend API | `[{ "agents": ["backend"], "tdd_parallel": true, "acceptance_criteria": ["AC-001"] }, ["reviewer"]]` |
| Full-stack | `[["designer"], { "agents": ["backend"], "tdd_parallel": true, "acceptance_criteria": ["AC-001"] }, ["reviewer"], { "agents": ["frontend"], "tdd_parallel": true, "acceptance_criteria": ["AC-002"] }, ["reviewer"]]` |
| UI only | `[["designer"], { "agents": ["frontend"], "tdd_parallel": true, "acceptance_criteria": ["AC-001"] }, ["reviewer"]]` |
| Tooling / docs / config | `[{ "agents": ["backend"], "tdd_parallel": true, "acceptance_criteria": ["AC-001"] }, ["reviewer"]]` for code-touching tooling; `["documenter", { "agents": ["reviewer"], "requires_test_execution": false }]` for docs-only |
| CI/CD / infra | `[["devops"], ["reviewer"]]` |
| Feature + deploy | `[{ "agents": ["backend"], "tdd_parallel": true, "acceptance_criteria": ["AC-001"] }, ["reviewer"], ["devops"], ["reviewer"]]` |
| High-risk/user-facing QA validation | `[{ "agents": ["qa-owner"], "qa_mode": "plan" }, { "agents": ["backend"], "tdd_parallel": true, "acceptance_criteria": ["AC-001"] }, { "agents": ["qa-owner"], "qa_mode": "verify", "qa_loop_target": "previous_implementation", "acceptance_criteria": ["AC-001"] }, ["reviewer"]]` |

Only place agents in the same inner array when their outputs are **independent**
and the stage is not a code implementation stage that needs a TDD partner. If
an agent consumes another agent's artifact, put it in a later stage even when
both changes touch different files.

**Example pipeline.json:**
```json
{
  "task": "User authentication flow",
  "stages": [
    ["designer"],
    { "agents": ["backend"], "tdd_parallel": true, "acceptance_criteria": ["AC-001"] },
    ["reviewer"],
    { "agents": ["frontend"], "tdd_parallel": true, "acceptance_criteria": ["AC-002"] },
    ["reviewer"]
  ],
  "needs_creation": [],
  "completed_stages": 0,
  "branch": "feature/user-authentication-flow-YYYYMMDD-HHMMSS-0",
  "execution_mode": "single"
}
```

Use `qa-owner` when the task benefits from a professional QA owner:
user-facing behavior, bug fixes with reproduction steps, release-risk changes,
workflow regressions, multi-step business scenarios, or requests that explicitly
ask for test cases/TCs. QA planning produces `context/qa-test-cases.md` and
`context/qa-plan.md`; QA verification produces `context/qa-report.md` and
optionally `context/qa-defects.md`. The reviewer still follows QA verification
and remains the final code quality gate.

---

## Agent Sufficiency Evaluation

Before finalizing the pipeline, check whether each required role can be fulfilled by an existing agent:

- A new agent is needed if the task requires domain-specific knowledge a generic agent cannot reliably provide
- A new agent is needed if the workflow or output format differs significantly from any built-in agent
- A new agent is needed if more than two significant prompting workarounds would be required
- Bias toward creating new agents; only reuse existing agents when the match is unambiguous

**Built-in agents:** analyst, backend, designer, devops, documenter, frontend, planner, qa-owner, requirements, resolver, reviewer.

---

## Pipeline Validation

After writing pipeline.json, cross-check:
1. Every `needs_creation` entry name appears in at least one stage
2. Every non-builtin stage agent has a `needs_creation` entry
3. Every stage name is either a built-in agent or a planned custom agent
4. `completed_stages` is an integer and starts at `0` for new runs
5. `execution_mode` matches the orchestrator context (`single` or `parallel`)
6. Final stage is always `["reviewer"]`
7. Every PRD `AC-*` item is mapped into an implementation or QA-verification
   stage's `acceptance_criteria`
8. `pipeline-quality-plan-check.py --pipeline {TASK_DIR}/pipeline.json` passes
   for mutating implementation work

---

## Parallelization Cost/Benefit

Parallel stages introduce resolver overhead if the same file is modified. Apply this decision rule:

| Scenario | Decision |
|---|---|
| Agents touch entirely different files | Parallelize — no resolver cost |
| Agents touch same files, logically independent | Parallelize — resolver handles merge |
| Agent B needs Agent A's compiled output | Sequential — true data dependency |
| One agent is very fast (< 1 min) | Sequential may be simpler — weigh against fan-out overhead |

**Default rule:** parallelize. The resolver's purpose is to handle conflicts. Serializing to avoid conflicts trades throughput for a problem the resolver already solves.

---

## Handoff Document Authoring

Write a concise handoff.md that gives downstream agents exactly what they need without repeating the full PRD. Include:
- Summarized requirements and acceptance criteria
- Key technical decisions (language, framework, DB, auth method)
- Explicit constraints (must not change X, must use Y)
- The PRD path (`{TASK_DIR}/context/prd.md`)
- API contract location if available

---

## Checklist
- [ ] PRD written to `{TASK_DIR}/context/prd.md` with goals, features, NFRs, and scope
- [ ] PRD maintainability NFR names KISS, YAGNI, and DRY when implementation
      work is planned
- [ ] Core Features marked with MoSCoW priority
- [ ] At least one `AC-*` acceptance criterion per Must-have feature
- [ ] Dependency graph analyzed; critical path identified
- [ ] Existing agent list discovered (builtin + custom)
- [ ] Agent sufficiency evaluated for each required role
- [ ] `needs_creation` populated for any role that existing agents cannot fulfill
- [ ] `stages` follows canonical mapping, maps every PRD `AC-*`, and ends with `["reviewer"]`
- [ ] Parallel stages contain only independent agents (no data dependency between them)
- [ ] Parallelization cost/benefit analyzed for same-file overlap
- [ ] Pipeline validation passed (cross-referencing `needs_creation` and `stages`)
- [ ] `pipeline.json` written to `{TASK_DIR}/pipeline.json`
- [ ] `handoff.md` written to `{TASK_DIR}/handoff.md`
- [ ] Completion report returned in 3 lines or fewer
