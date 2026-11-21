# Skill: requirement-gathering

## Purpose
Run structured multi-round interviews, detect ambiguity, and return a validated
REQUIREMENTS block.

## When to Apply
- New task without a REQUIREMENTS block, planner delegation before PRD creation,
  or missing or contradictory scope, target, or constraints.

---

## User Story Format (Mike Cohn, "User Stories Applied", 2004)

Describe user value with a user story, then make it testable with acceptance
criteria:

```
As a <role>,
I want <capability>,
So that <business value>.
```

**Example:**
```
As a store manager,
I want to filter orders by status and date range,
So that I can quickly identify pending orders that need attention.
```

---

## INVEST Criteria (Bill Wake, 2003)

Each user story should be:

| Letter | Property | Check |
|---|---|---|
| I | **Independent** | Can be delivered without depending on another story |
| N | **Negotiable** | Details can be adjusted between team and customer |
| V | **Valuable** | Delivers value to the user or customer |
| E | **Estimable** | Small enough to estimate effort |
| S | **Small** | Fits in one sprint / one task |
| T | **Testable** | Has clear acceptance criteria |

Flag stories that fail multiple INVEST criteria as under-specified.

---

## MoSCoW Prioritization (Dai Clegg, DSDM 1994)

Use when the scope includes multiple features competing for priority:

| Category | Meaning |
|---|---|
| **Must have** | Non-negotiable; MVP fails without it |
| **Should have** | Important but not critical for launch |
| **Could have** | Nice-to-have; include only if time permits |
| **Won't have (this time)** | Explicitly out of scope for this iteration |

Record the classification in `requirements.md` under a `priority:` field.

---

## Acceptance Criteria — Given/When/Then (Gherkin)

(Reference: Cucumber / Behaviour-Driven Development, Dan North, 2006)

Write testable acceptance criteria in Gherkin format:

```gherkin
Feature: Order status filter

  Scenario: AC-001 - Filter orders by PENDING status
    Given there are 10 orders with PENDING status and 5 with PAID status
    When the manager filters orders by "PENDING"
    Then only 10 orders are shown
    And each row displays status "PENDING"

  Scenario: AC-002 - Empty result set
    Given there are no CANCELLED orders
    When the manager filters orders by "CANCELLED"
    Then an empty state message "No orders found" is displayed
```

Each acceptance criterion must have a stable `AC-*` identifier so the planner
can map it into `pipeline.json` stage `acceptance_criteria` entries. Each
criterion becomes a test case for the reviewer agent's coverage matrix.

---

## Pre-Supplied Requirements Handling

Treat a supplied `REQUIREMENTS` block or equivalent explicit answers as
completed interview input. Validate `scope`, `target`, and `constraints`,
normalize ambiguous free text to the closest supported category, and record
`source: provided` in `{TASK_DIR}/context/requirements.md`. Ask only about
missing or contradictory fields.

---

## Structured Round-1 Interview

Always begin with three fixed questions covering Scope, Target, and Constraints. Use the host AI tool's structured choice UI with predefined options — never open-ended text prompts.

```
Q1 Scope   → "Backend API" | "Full-stack" | "UI only" | "Tooling / docs / config"
Q2 Target  → "Internal team" | "End-user product" | "Developer tooling" | "Other"
Q3 Constraints → multiSelect: ["Use existing tech stack only", "MVP", "Performance", "No special constraints"]
```

---

## Ambiguity Detection

After Round 1, scan answers for signals of under-specified scope:
- Scope = "Tooling / docs / config" → skip domain-specific Round 2
- Scope involves agent files, prompts, rules, docs, adapter templates, or command definitions → classify as "Tooling / docs / config"
- Target = "Other / not yet defined" → note ambiguity but do not block progress
- Contradictory answers (e.g., "UI only" + database constraint) → flag and clarify in Round 2
- A request to "review", "strengthen", "document", or "improve guidance" without product-facing behavior → tooling/docs scope

---

## Domain-Specific Round-2 Follow-up

| Scope | Q-A | Q-B |
|---|---|---|
| Backend API | Database choice | Auth method |
| Full-stack | State management | Database choice |
| UI only | State management | Design system choice |

---

## Non-Functional Requirements Categories

Capture NFRs explicitly.

| Category | Example Questions |
|---|---|
| **Performance** | Max response time? Expected concurrent users? |
| **Scalability** | Expected data volume growth? Horizontal scaling needed? |
| **Security** | Auth method? PII involved? Compliance (GDPR, HIPAA)? |
| **Availability** | SLA? Acceptable downtime window? |
| **Observability** | Logging required? Metrics/alerts? Distributed tracing? |
| **Maintainability** | Code coverage target? Linting rules? |

---

## Requirements Block Formatting

```text
source: asked | provided
scope: {r1_scope}
target: {r1_target}
constraints: {r1_constraints}
priority: {must/should/could/wont}
acceptance_criteria:
  - AC-001: Given {condition} When {action} Then {outcome}
followup:
  {key}: {value}
nfr:
  performance: {value}
  security: {value}
```

---

## Idempotent File Writing

```bash
mkdir -p "{TASK_DIR}/context"
# Write to requirements.md before returning inline block
```

---

## Checklist
- [ ] Pre-supplied REQUIREMENTS block validated, or Round 1 questions asked using structured choice UI
- [ ] `r1_scope`, `r1_target`, `r1_constraints` recorded from Round 1
- [ ] Ambiguity detection performed after Round 1
- [ ] Round 2 questions asked only for missing or domain-specific fields
- [ ] User stories written in "As a / I want / So that" format for each core feature
- [ ] Each user story validated against INVEST criteria
- [ ] MoSCoW priority recorded for each feature
- [ ] At least one `AC-*` acceptance criterion per must-have story
- [ ] NFR categories covered (performance, security, availability)
- [ ] `{TASK_DIR}/context/requirements.md` written successfully
- [ ] REQUIREMENTS block returned inline to the caller
- [ ] No missing requirements inferred from the task description without asking
