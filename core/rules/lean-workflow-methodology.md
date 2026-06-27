---
name: lean-workflow-methodology
description: >
  Provider-neutral lightweight workflow methodology for agent-crew commands,
  agents, and retry loops. Use to keep orchestration thin, context small, and
  review loops bounded while preserving agent-first execution.
applies-to: run.md, analyst, planner, supervisor, reviewer, test-writer, backend, frontend
---

# Lean Workflow Methodology

agent-crew uses this rule as the shared workflow method for command and agent
prompts. It adapts the useful cowave patterns into provider-neutral agent-crew
terms. The rule is not tied to any host adapter, model, or vendor-specific
skill surface.

## Thin Harness, Fat Rules

Command and agent files should describe routing, phase order, inputs, and output
contracts. Shared method belongs in rule files such as this one and in
project-local policy documents. Do not copy long methodology blocks into every
command or agent.

When a prompt needs one of these workflow principles, link this file and state
which phase applies.

## Phase Grammar

Use this public phase vocabulary for non-trivial implementation work:

```text
Align -> Plan -> Execute/TDD -> Review
```

- **Align**: clarify objective, scope boundary, target artifact, and known
  exclusions. Short, unambiguous tasks may pass with a one-line assumption.
- **Plan**: produce the minimum PRD, pipeline, and handoff needed for the next
  agent. Prefer concrete paths and acceptance criteria over broad prose.
- **Execute/TDD**: make the smallest behavior change that satisfies the plan.
  For testable code behavior, identify the focused test target before production
  mutation.
- **Review**: run an independent read-only quality pass. Re-review should verify
  prior Must findings before starting a new broad sweep.

The phase labels are operator-facing simplifications. They do not replace the
existing `pipeline.json`, progress events, quality-loop, or reviewer contracts.

## Context Diet

Minimize token load before adding more process.

- Do not inline broad file dumps into handoffs, reviewer prompts, status output,
  or retry directives.
- Return conclusions, file:line references, and risks instead of copied source
  blocks.
- Pass large artifacts by path, not by content, when the next step can read the
  file directly.
- When a subagent or capability dispatcher performs a wide scan, the main prompt
  should receive the matched paths, decision context, and concrete gaps only.
- Prefer deterministic script output for repeated checks instead of asking the
  model to restate proof artifacts.

## Workflow Origin vs Target Scope

Workflow notation such as `crew:run`, `$crew-run`, or a host wrapper skill is the
origin of execution unless the user explicitly makes that command, wrapper,
file, or `SKILL.md` the review target.

Examples:

- `$crew-run 코드리뷰` means run the code-review task through the crew-run
  workflow.
- `` `$crew-run` skill을 코드리뷰해 `` means review the wrapper skill itself.

If the distinction is ambiguous, use the structured disambiguation rule. Do not
silently reinterpret the workflow command token as a target artifact.

## Review Loop Boundaries

The first review may be a full scan. A retry review should default to
`verify-prior-must-only`: first verify that prior Must findings were fixed.
New Must findings during re-review require a classification and concrete
first-party evidence. Weakly evidenced findings remain Should/MINOR.

Reviewer output or protocol defects retry the reviewer only and must not consume
the implementer retry budget. Repeated reviewer-protocol failures block with a
reviewer-loop blocker instead of creating an implementation loop.

## Fake Completion Guard

Completion must be based on changed behavior, tests, reviews, and runtime
checks. It must not pass when changed executable files still contain known fake
completion markers such as TODO/FIXME placeholders, disabled or focused tests,
or explicit not-implemented stubs.

This guard should be implemented by deterministic changed-file scanning. Do not
ask agents to create a separate proof artifact just to prove the absence of
fake-completion markers.

## Optional External Systems

Issue trackers, MR systems, and external knowledge tools are adapters, not core
workflow requirements. If they are unavailable or fail, the workflow should keep
local state and continue when the task itself can still be completed safely.

Provider-specific behavior belongs in host adapters or user-owned skills, not
in core rule prose.
