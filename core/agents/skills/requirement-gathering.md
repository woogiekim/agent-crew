# Skill: requirement-gathering

## Purpose
Enables the requirements agent to conduct structured multi-round interviews, detect ambiguity in user input, and produce a validated REQUIREMENTS block that downstream agents can consume without further clarification.

## When to Apply
- Whenever a new task arrives without a pre-existing REQUIREMENTS block
- When the planner delegates requirement collection before PRD creation
- When scope, target, or constraints are undefined or contradictory

## Techniques

### Structured Round-1 Interview
Always begin with three fixed questions covering Scope, Target, and Constraints. Use the host AI tool's structured choice UI with predefined options — never open-ended text prompts.

**Example flow:**
```
Q1 Scope   → "Backend API" | "Full-stack" | "UI only" | "Tooling / docs / config"
Q2 Target  → "Internal team" | "End-user product" | "Developer tooling" | "Other"
Q3 Constraints → multiSelect: ["Use existing tech stack only", "MVP", "Performance", "No special constraints"]
```

### Ambiguity Detection
After Round 1, scan answers for signals that indicate under-specified scope:
- Scope = "Tooling / docs / config" → skip domain-specific Round 2
- Target = "Other / not yet defined" → note ambiguity but do not block progress
- Contradictory answers (e.g., "UI only" + database constraint) → flag and clarify in Round 2

### Domain-Specific Round-2 Follow-up
Run tailored follow-up questions based on the Round-1 scope answer. Each domain has two follow-up questions:

| Scope       | Q-A                  | Q-B                   |
|-------------|----------------------|-----------------------|
| Backend API | Database choice      | Auth method           |
| Full-stack  | State management     | Database choice       |
| UI only     | State management     | Design system choice  |

### Requirements Block Formatting
Produce a machine-readable block that planner and pipeline agents can parse without reading the full file:

```text
scope: {r1_scope}
target: {r1_target}
constraints: {r1_constraints}
followup:
  {key}: {value}
```

### Idempotent File Writing
Always write `{TASK_DIR}/context/requirements.md` before returning the inline block. Ensure the `context/` directory exists first:

```bash
mkdir -p "{TASK_DIR}/context"
```

## Checklist
- [ ] Round 1 questions asked using structured choice UI (no plain-text prompts)
- [ ] `r1_scope`, `r1_target`, `r1_constraints` recorded from Round 1
- [ ] Ambiguity detection performed after Round 1
- [ ] Round 2 questions asked when scope is not "Tooling / docs / config"
- [ ] `{TASK_DIR}/context/requirements.md` written successfully
- [ ] REQUIREMENTS block returned inline to the caller
- [ ] No requirements inferred from the task description without asking
