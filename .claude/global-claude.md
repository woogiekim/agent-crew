# agent-crew — Global Rules (Applied to All Projects)

## ⛔ No Direct Implementation

When a user requests coding, implementation, or development work, **do not start Edit·Write·code generation directly**.
Always follow the sequence below:

1. Determine the request type
2. Execute the appropriate agent or skill first
3. Implementation happens only inside agents

This is a **system behavior principle**, not a Claude preference or memory setting.
The `UserPromptSubmit` hook detects development requests and enforces this rule.

## Agent Routing Criteria

| Request Type | Execution Method |
|---------|---------|
| Backend API, domain logic, DB | `Agent(subagent_type="backend", ...)` |
| UI/screen implementation | `/task` → designer → frontend |
| Full-stack / unclear scope | `/task` → planner determines pipeline |
| Multiple independent features | `/crew "featureA" "featureB" ...` |
| Requirements analysis only | `Agent(subagent_type="planner", ...)` |

## Auto-Execution Triggers

**Spawn an agent when**:
- Korean action verbs: "만들어줘", "구현해줘", "개발해줘", "추가해줘", "수정해줘" + development content
- English action verbs: "rename", "refactor", "update", "fix", "add", "remove", "move", "change", "migrate", "modify", "replace", "extend", "integrate" + development content
- **Simple confirmation words**: "go", "yes", "ok", "진행", "확인", "ㅇㅇ", "응", "그래", "해줘", "계속", etc. → If the prior conversation context was about implementation or development work, always process through the /task pipeline. It is forbidden to classify simple confirmation words as questions/explanations and respond directly.

**Respond directly (no agent)**: "how", "explain", "why", "what", "어떻게", "설명해", "왜", "무엇" → direct answer if it is a question

## Available Skills / Commands

```
/setup    # Initialize project workspace (run once)
/task     # Full pipeline for a single task (planner → implementation agents)
/crew     # Parallel execution of multiple independent tasks (each in isolated worktree)
/cost     # Session cost summary
```

State directory is auto-created in `~/.claude/agent-crew/{PROJECT_NAME}/tasks/{TASK_ID}` format if it does not exist.

## AskUserQuestion Rules

- Do not add "직접 입력", "기타 입력", "텍스트로 입력" or similar free-text options to the choices list.
- AskUserQuestion always provides an "Other" free-text field automatically — adding one is redundant.

## Subagent Plan Approval Rule

All subagents (backend, frontend, designer, etc.) must do the following before starting implementation.
The planner is exempt since planning itself is its role.

1. **Write a plan summary** — include the following:
   - What to implement and why
   - Approach (pattern/methodology)
   - List of files to create/modify
   - Estimated number of implementation steps

2. **Request approval via AskUserQuestion** — options:
   - "Approve — proceed as planned" → start implementation immediately
   - "Request changes — revise plan and re-approve" → reflect the Other input and re-present the revised plan (loop)
   - "Cancel — stop implementation" → report `STATUS: cancelled` to parent and exit immediately

**Standard plan summary format**:
```
[agent-name] Work Plan

Target: {feature name}
Approach: {pattern/methodology summary}
Files:
  - {file path 1} (new/modified)
  - {file path 2} (new/modified)
Estimated steps: {number of steps or TDD cycles}

Proceed with this plan?
```
