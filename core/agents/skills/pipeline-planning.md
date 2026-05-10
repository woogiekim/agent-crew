# Skill: pipeline-planning

## Purpose
Enables the planner agent to translate a structured requirements block into a concrete agent pipeline, produce a PRD, and write handoff artifacts that downstream agents can consume immediately without further clarification.

## When to Apply
- After requirements have been collected (either passed in or gathered via the requirements agent)
- When a request spans multiple domains (backend + frontend, feature + deploy, etc.)
- When the correct agent sequence or parallelization strategy is unclear
- When evaluating whether a custom agent is needed for a specialized role

## Techniques

### PRD Authoring from Requirements
Translate scope/target/constraints answers into a structured Product Requirements Document. Keep goals declarative and implementation-agnostic.
For tooling, documentation, prompt, or agent-skill work, frame the PRD around
workflow reliability and safety rather than product screens or API behavior.

**PRD structure:**
```markdown
# PRD: {feature name}

## Goals
- {what the feature achieves}

## Core Features
- {feature 1}
- {feature 2}

## Non-Functional Requirements
- Performance: ...
- Security: ...

## Scope
In: ...
Out: ...
```

### Agent Sufficiency Evaluation
Before finalizing the pipeline, systematically check whether each role required by the task can be fulfilled by an existing agent. Use the decision criteria below:

- A new agent is needed if the task requires domain-specific knowledge a generic agent cannot reliably provide
- A new agent is needed if the workflow or output format differs significantly from any built-in agent
- A new agent is needed if more than two significant prompting workarounds would be required
- Bias toward creating new agents; only reuse existing agents when the match is unambiguous

### Pipeline Stage Composition
Build `stages` as a 2D array where inner arrays run in parallel and outer arrays run sequentially. Apply the canonical mapping:

| Scope | stages |
|---|---|
| Backend API | `[["backend"], ["reviewer"]]` |
| Full-stack | `[["designer", "backend"], ["frontend"], ["reviewer"]]` |
| UI only | `[["designer"], ["frontend"], ["reviewer"]]` |
| Tooling / docs / config | `[["backend"], ["reviewer"]]` unless a dedicated custom agent is created |
| CI/CD / infra | `[["devops"], ["reviewer"]]` |
| Feature + deploy | `[["backend"], ["devops"], ["reviewer"]]` |

Only place agents in the same inner array when their outputs are independent.
If an agent consumes another agent's artifact, put it in a later stage even when
both changes touch different files.

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

### Pipeline Validation
After writing pipeline.json, cross-check:
1. Every `needs_creation` entry name appears in at least one stage
2. Every non-builtin stage agent has a `needs_creation` entry
3. Every stage name is either a built-in agent or a planned custom agent
4. `completed_stages` is an integer and starts at `0` for new runs
5. `execution_mode` matches the orchestrator context (`single` or `parallel`)

### Handoff Document Authoring
Write a concise handoff.md that gives downstream agents exactly what they need without repeating the full PRD. Include: summarized requirements, key technical decisions, constraints, and the PRD path.

## Checklist
- [ ] PRD written to `{TASK_DIR}/context/prd.md` with goals, features, and NFRs
- [ ] Existing agent list discovered (builtin + custom)
- [ ] Agent sufficiency evaluated for each required role
- [ ] `needs_creation` populated for any role that existing agents cannot fulfill
- [ ] `stages` follows canonical mapping and ends with `["reviewer"]`
- [ ] Parallel stages contain only independent agents
- [ ] Pipeline validation passed (cross-referencing `needs_creation` and `stages`)
- [ ] `pipeline.json` written to `{TASK_DIR}/pipeline.json`
- [ ] `handoff.md` written to `{TASK_DIR}/handoff.md`
- [ ] Completion report returned in 3 lines or fewer
