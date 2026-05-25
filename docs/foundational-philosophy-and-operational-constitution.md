# Define foundational philosophy and operational constitution

This document defines the permanent philosophical and operational foundation of
agent-crew.

This project must not evolve into:
- a simple AI coding tool
- a prompt wrapper
- a generic multi-agent toy framework

The long-term direction is:

```text
Persistent AI Workforce System
```

## Core Identity

agent-crew is an:

```text
AI Development Operating System
```

Its purpose is not merely generating code.

Its purpose is:

```text
AI continuously performing work
```

through:

- workflow execution
- task orchestration
- persistent state
- recovery
- resume
- approval flow
- operational continuity

## Permanent Core Principles

### 1. Workflow durability is more important than model capability

The system must prioritize:
- reliability
- resumability
- continuity
- deterministic execution

over:
- raw model intelligence
- agent count
- benchmark performance

### 2. AI must sustain long-running work

AI should not terminate after response generation.

The system must support:
- long-running execution
- interruption recovery
- persistent workflows
- resumable tasks
- checkpointing

### 3. Human-in-the-loop is mandatory

Dangerous operations must never become fully autonomous by default.

Examples:
- production deploy
- destructive migration
- git push
- infrastructure modification
- secret handling

Required structure:

```text
AI proposes
-> Human approves
-> AI executes
```

### 4. Roles and responsibilities must be explicit

The project should evolve around:
- role contracts
- execution boundaries
- workflow responsibility
- state ownership

rather than uncontrolled agent proliferation.

### 5. State persistence is a first-class concern

Execution state must survive:
- crashes
- interruption
- token limits
- runtime restart
- partial failure

### 6. Separation of concerns must be preserved

The following concerns must remain decoupled:
- execution
- planning
- memory
- tooling
- approval
- orchestration

### 7. Deterministic workflow behavior is preferred

The same workflow should produce predictable operational behavior whenever
possible.

## Foundational Statement

```text
AI should not merely generate responses.
AI should continuously perform work.
```

This philosophy must guide:
- architecture
- workflow design
- plugin systems
- runtime behavior
- future roadmap decisions
