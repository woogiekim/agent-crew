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
- Given {context} When {action} Then {outcome}

## Non-Functional Requirements
- Performance: {response time / throughput target}
- Security: {auth, data handling}
- Availability: {SLA}

## Scope
In: {explicitly included}
Out: {explicitly excluded}
```

---

## Stage Dependency Analysis — Critical Path

Before assigning agents to stages, map data dependencies:

1. List every artifact each agent **produces** and **consumes**.
2. Draw a dependency graph (can be mental or written).
3. Agents with no dependency on each other's outputs → same stage (parallel).
4. Agent B that consumes Agent A's output → later stage (sequential).

```
designer produces: design-spec.md
backend  produces: OpenAPI contract, DB schema
frontend consumes: design-spec.md + OpenAPI contract

→ designer and backend can run in parallel (Stage 1)
→ frontend must follow both (Stage 2)
```

**Critical path rule:** the pipeline duration is bounded by the longest sequential chain, not the sum of all work. Maximize parallelism on the critical path.

---

## Pipeline Stage Composition

Build `stages` as a 2D array where inner arrays run in parallel and outer arrays run sequentially.

| Scope | stages |
|---|---|
| Backend API | `[["backend"], ["reviewer"]]` |
| Full-stack | `[["designer", "backend"], ["frontend"], ["reviewer"]]` |
| UI only | `[["designer"], ["frontend"], ["reviewer"]]` |
| Tooling / docs / config | `[["backend"], ["reviewer"]]` unless a dedicated custom agent is created |
| CI/CD / infra | `[["devops"], ["reviewer"]]` |
| Feature + deploy | `[["backend"], ["devops"], ["reviewer"]]` |

Only place agents in the same inner array when their outputs are **independent**. If an agent consumes another agent's artifact, put it in a later stage even when both changes touch different files.

**Example pipeline.json:**
```json
{
  "task": "User authentication flow",
  "stages": [["designer", "backend"], ["frontend"], ["reviewer"]],
  "needs_creation": [],
  "completed_stages": 0,
  "branch": "feature/user-authentication-flow-YYYYMMDD-HHMMSS-0",
  "execution_mode": "single"
}
```

---

## Agent Sufficiency Evaluation

Before finalizing the pipeline, check whether each required role can be fulfilled by an existing agent:

- A new agent is needed if the task requires domain-specific knowledge a generic agent cannot reliably provide
- A new agent is needed if the workflow or output format differs significantly from any built-in agent
- A new agent is needed if more than two significant prompting workarounds would be required
- Bias toward creating new agents; only reuse existing agents when the match is unambiguous

**Built-in agents:** analyst, backend, designer, devops, documenter, frontend, planner, requirements, resolver, reviewer.

---

## Pipeline Validation

After writing pipeline.json, cross-check:
1. Every `needs_creation` entry name appears in at least one stage
2. Every non-builtin stage agent has a `needs_creation` entry
3. Every stage name is either a built-in agent or a planned custom agent
4. `completed_stages` is an integer and starts at `0` for new runs
5. `execution_mode` matches the orchestrator context (`single` or `parallel`)
6. Final stage is always `["reviewer"]`

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
- [ ] Core Features marked with MoSCoW priority
- [ ] At least one acceptance criterion per Must-have feature
- [ ] Dependency graph analyzed; critical path identified
- [ ] Existing agent list discovered (builtin + custom)
- [ ] Agent sufficiency evaluated for each required role
- [ ] `needs_creation` populated for any role that existing agents cannot fulfill
- [ ] `stages` follows canonical mapping and ends with `["reviewer"]`
- [ ] Parallel stages contain only independent agents (no data dependency between them)
- [ ] Parallelization cost/benefit analyzed for same-file overlap
- [ ] Pipeline validation passed (cross-referencing `needs_creation` and `stages`)
- [ ] `pipeline.json` written to `{TASK_DIR}/pipeline.json`
- [ ] `handoff.md` written to `{TASK_DIR}/handoff.md`
- [ ] Completion report returned in 3 lines or fewer
